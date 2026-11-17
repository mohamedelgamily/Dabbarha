import * as SecureStore from 'expo-secure-store';
import { z } from 'zod';
import { assertSession, authStorageTask } from '@/api/session';
import { logoutMarkerKey, v2SessionStorageKey, clearAuthStorage, AuthStorageCleanupError, STORAGE_UNSAFE_MESSAGE } from './storage';

const credential = z.string().regex(/^[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]$/);
const seconds = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
const pendingSchema = z.object({
  originalRefreshToken: credential,
  retryKey: credential,
  preparedAt: seconds,
  attempts: z.number().int().min(0).max(3).optional(),
  retryAfterAt: seconds.optional(),
  stopped: z.boolean().optional(),
}).strict();
const recordSchema = z.object({
  version: z.literal(1),
  userId: z.number().int().positive().max(Number.MAX_SAFE_INTEGER),
  sessionId: z.string().uuid(),
  refreshToken: credential,
  refreshExpiresAt: seconds,
  sessionExpiresAt: seconds,
  pending: pendingSchema.nullable(),
}).strict().refine(record => record.refreshExpiresAt <= record.sessionExpiresAt &&
  (!record.pending || (record.pending.originalRefreshToken === record.refreshToken &&
    record.pending.preparedAt < record.refreshExpiresAt)), 'Invalid session record');

export type SavedSession = z.infer<typeof recordSchema>;
export type SessionStorageScope = { generation: number; userId: number; sessionId: string };
export type SessionReadResult =
  | { status: 'missing' | 'blocked' | 'invalid' | 'expired' | 'recovery-unavailable' }
  | { status: 'ready' | 'pending'; record: SavedSession };

function validate(value: unknown): SavedSession {
  const parsed = recordSchema.safeParse(value);
  // Do not expose Zod errors containing credential input to callers/logs.
  if (!parsed.success) throw new Error('Invalid session record');
  return parsed.data;
}
function identity(record: SavedSession, scope: SessionStorageScope) {
  assertSession(scope.generation);
  if (record.userId !== scope.userId || record.sessionId !== scope.sessionId) throw new Error('Session identity changed');
}
async function unblocked() {
  if (await SecureStore.getItemAsync(logoutMarkerKey)) throw new Error('Session restoration blocked');
}
async function stored(): Promise<SavedSession | null> {
  const raw = await SecureStore.getItemAsync(v2SessionStorageKey);
  if (!raw) return null;
  try { return validate(JSON.parse(raw)); } catch { throw new Error('Invalid session record'); }
}
const nowSeconds = () => Math.floor(Date.now() / 1000);

// Capture after any already-started native write, then delete in the same queue
// slot. A new account cannot write between credential capture and cleanup.
// Expired/consumed refresh tokens can still identify a session for backend logout.
export function clearStoredSessionForLogout(generation: number, userId?: number) {
  return authStorageTask(async () => {
    assertSession(generation);
    let refreshToken: string | null = null;
    let credentialUnavailable = false;
    let cleanupError: string | null = null;
    // Make logout intent durable before reading a credential for revocation.
    // clearAuthStorage retries this marker and retains its existing fallback.
    try { await SecureStore.setItemAsync(logoutMarkerKey, '1'); } catch { /* Still attempt cleanup. */ }
    try {
      const record = await stored();
      if (record && userId !== undefined && record.userId !== userId) credentialUnavailable = true;
      else refreshToken = record?.refreshToken ?? null;
    }
    catch { credentialUnavailable = true; }
    try { await clearAuthStorage(); }
    catch (error) { cleanupError = error instanceof AuthStorageCleanupError ? error.message : STORAGE_UNSAFE_MESSAGE; }
    return { refreshToken, credentialUnavailable, cleanupError };
  });
}

// All public operations use the SAME queue as legacy auth persistence/cleanup.
// Call these directly, never from inside authStorageTask (which is not reentrant).
export function readSessionRecord(generation: number, now = nowSeconds()): Promise<SessionReadResult> {
  return authStorageTask(async () => {
    assertSession(generation);
    if (await SecureStore.getItemAsync(logoutMarkerKey)) { assertSession(generation); return { status: 'blocked' }; }
    const raw = await SecureStore.getItemAsync(v2SessionStorageKey);
    assertSession(generation);
    if (raw === null) return { status: 'missing' };
    let record: SavedSession;
    try { record = validate(JSON.parse(raw)); } catch { return { status: 'invalid' }; }
    if (record.sessionExpiresAt <= now) return { status: 'expired' };
    if (record.pending) {
      // Conservative client bound, not an assertion of the server receipt deadline.
      if (record.pending.preparedAt > now || now - record.pending.preparedAt >= 60) return { status: 'recovery-unavailable' };
      return { status: 'pending', record };
    }
    return record.refreshExpiresAt <= now ? { status: 'expired' } : { status: 'ready', record };
  });
}

export function saveNewSession(scope: SessionStorageScope, input: SavedSession, now = nowSeconds()): Promise<void> {
  const record = validate(input);
  return authStorageTask(async () => {
    identity(record, scope); await unblocked();
    if (record.pending || record.refreshExpiresAt <= now || record.sessionExpiresAt <= now) throw new Error('Invalid new session');
    // Replacement requires explicit logout cleanup, never silently replaces an account.
    if (await stored()) throw new Error('Saved session already exists');
    identity(record, scope);
    await SecureStore.setItemAsync(v2SessionStorageKey, JSON.stringify(record));
    identity(record, scope);
  });
}

export function prepareRefresh(scope: SessionStorageScope, retryKey: string, now = nowSeconds()): Promise<SavedSession> {
  return authStorageTask(async () => {
    assertSession(scope.generation); await unblocked();
    const record = await stored();
    if (!record) throw new Error('No saved session');
    identity(record, scope);
    // An ambiguous operation is immutable, including across restarts.
    if (record.pending) {
      if (record.pending.retryKey !== retryKey) throw new Error('Refresh operation already pending');
      if (record.sessionExpiresAt <= now || record.pending.preparedAt > now || now - record.pending.preparedAt >= 60) throw new Error('Refresh recovery unavailable');
      return record;
    }
    if (record.refreshExpiresAt <= now || record.sessionExpiresAt <= now) throw new Error('Session expired');
    const next = validate({ ...record, pending: { originalRefreshToken: record.refreshToken, retryKey, preparedAt: now } });
    identity(next, scope);
    await SecureStore.setItemAsync(v2SessionStorageKey, JSON.stringify(next));
    identity(next, scope);
    return next;
  });
}

export function saveRefreshSuccessor(scope: SessionStorageScope, operation: NonNullable<SavedSession['pending']>, input: SavedSession, now = nowSeconds()): Promise<void> {
  const next = validate(input);
  return authStorageTask(async () => {
    identity(next, scope); await unblocked();
    const previous = await stored();
    if (!previous) throw new Error('No saved session');
    identity(previous, scope);
    if (!previous.pending || previous.pending.originalRefreshToken !== operation.originalRefreshToken ||
      previous.pending.retryKey !== operation.retryKey || previous.pending.preparedAt !== operation.preparedAt) throw new Error('Refresh operation changed');
    if (next.pending || next.refreshToken === previous.refreshToken || next.sessionExpiresAt !== previous.sessionExpiresAt ||
      next.refreshExpiresAt <= now || next.refreshExpiresAt < previous.refreshExpiresAt) throw new Error('Invalid refresh successor');
    identity(next, scope);
    // One native record replacement both saves the successor and removes pending.
    // On rejection the caller must not publish success; read back before recovery.
    await SecureStore.setItemAsync(v2SessionStorageKey, JSON.stringify(next));
    identity(next, scope);
  });
}

/** Reserve a send durably. A crash may waste an attempt, but cannot reset its budget. */
export function reserveRefreshAttempt(scope: SessionStorageScope, operation: NonNullable<SavedSession['pending']>, now = nowSeconds()): Promise<SavedSession> {
  return authStorageTask(async () => {
    assertSession(scope.generation); await unblocked();
    const record = await stored();
    if (!record) throw new Error('No saved session');
    identity(record, scope);
    const pending = record.pending;
    if (!pending || pending.retryKey !== operation.retryKey || pending.originalRefreshToken !== operation.originalRefreshToken || pending.preparedAt !== operation.preparedAt) throw new Error('Refresh operation changed');
    if (pending.stopped || (pending.retryAfterAt ?? 0) > now || now < pending.preparedAt || now - pending.preparedAt >= 60 || record.sessionExpiresAt <= now || (pending.attempts ?? 0) >= 3) throw new Error('Refresh recovery unavailable');
    const next = validate({ ...record, pending: { ...pending, attempts: (pending.attempts ?? 0) + 1 } });
    identity(next, scope);
    await SecureStore.setItemAsync(v2SessionStorageKey, JSON.stringify(next));
    identity(next, scope);
    return next;
  });
}

export function saveRefreshOutcome(scope: SessionStorageScope, operation: NonNullable<SavedSession['pending']>, outcome: { stopped?: boolean; retryAfterAt?: number }): Promise<void> {
  return authStorageTask(async () => {
    assertSession(scope.generation); await unblocked();
    const record = await stored();
    if (!record) throw new Error('No saved session');
    identity(record, scope);
    if (!record.pending || record.pending.retryKey !== operation.retryKey || record.pending.originalRefreshToken !== operation.originalRefreshToken || record.pending.preparedAt !== operation.preparedAt) throw new Error('Refresh operation changed');
    const next = validate({ ...record, pending: { ...record.pending, ...outcome } });
    identity(next, scope);
    await SecureStore.setItemAsync(v2SessionStorageKey, JSON.stringify(next));
    identity(next, scope);
  });
}
