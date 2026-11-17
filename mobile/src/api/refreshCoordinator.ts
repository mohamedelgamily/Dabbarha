import { CanceledError } from 'axios';
import { sessionsApi } from './sessions';
import { assertSession, sessionSnapshot, setSessionToken } from './session';
import { generateRefreshRetryKey } from '@/utils/refreshRetryKey';
import { readSessionRecord, prepareRefresh, reserveRefreshAttempt, saveRefreshSuccessor, saveRefreshOutcome,
  type SavedSession, type SessionStorageScope } from '@/utils/sessionStorage';
import type { SessionToken } from '@/types/session';

export class RefreshFailure extends Error {
  constructor(public readonly kind: 'reauthenticate' | 'temporary' | 'storage' | 'invalid-response' | 'invalid-request',
    public readonly statusCode?: number, public readonly detail?: string, public readonly retryAfter?: string) {
    super(`Refresh ${kind}`);
  }
}
const nowSeconds = () => Math.floor(Date.now() / 1000);
function pause(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new CanceledError('Session ended')); return; }
    const abort = () => { clearTimeout(timer); reject(new CanceledError('Session ended')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    signal.addEventListener('abort', abort, { once: true });
  });
}
function retryDelay(header: unknown, attempt: number, now: number) {
  if (typeof header === 'string') {
    const seconds = /^\d+$/.test(header) ? Number(header) : (Date.parse(header) / 1000) - now;
    if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
  }
  return Math.min(1000 * 2 ** (attempt - 1), 4000);
}

// Injectable clock/wait/transport for tests; production storage and guards stay real.
export function createRefreshCoordinator(deps: {
  refresh?: typeof sessionsApi.refresh;
  now?: () => number;
  wait?: typeof pause;
  retryKey?: typeof generateRefreshRetryKey;
} = {}) {
  const transport = deps.refresh ?? sessionsApi.refresh;
  const now = deps.now ?? nowSeconds;
  const wait = deps.wait ?? pause;
  const flights = new Map<number, { identity: string; promise: Promise<SessionToken> }>();
  function check(scope: SessionStorageScope, record?: SavedSession) {
    assertSession(scope.generation);
    if (record && (record.userId !== scope.userId || record.sessionId !== scope.sessionId)) throw new RefreshFailure('reauthenticate');
  }
  async function read(scope: SessionStorageScope) {
    check(scope);
    let result;
    try { result = await readSessionRecord(scope.generation, now()); }
    catch { check(scope); throw new RefreshFailure('storage'); }
    check(scope);
    if (result.status !== 'ready' && result.status !== 'pending') throw new RefreshFailure('reauthenticate');
    check(scope, result.record);
    return result.record;
  }
  async function run(scope: SessionStorageScope): Promise<SessionToken> {
    let record = await read(scope);
    if (!record.pending) {
      const key = await (deps.retryKey ?? generateRefreshRetryKey)(); check(scope);
      try { await prepareRefresh(scope, key, now()); }
      catch { check(scope); /* An ambiguous write must be verified before sending. */ }
      record = await read(scope);
      if (!record.pending || record.pending.retryKey !== key) throw new RefreshFailure('storage');
    }
    const original = record.pending!;
    const deadline = Math.min(original.preparedAt + 60, record.sessionExpiresAt);
    while (true) {
      check(scope);
      if (record.pending?.stopped) throw new RefreshFailure('reauthenticate');
      const notBefore = record.pending?.retryAfterAt ?? 0;
      if (notBefore > now()) {
        if (notBefore >= deadline) throw new RefreshFailure('temporary', undefined, undefined, String(notBefore - now()));
        await wait((notBefore - now()) * 1000, sessionSnapshot().signal); check(scope);
      }
      if (now() < original.preparedAt || now() >= deadline || (record.pending?.attempts ?? 0) >= 3) throw new RefreshFailure('reauthenticate');
      const intendedAttempt = (record.pending?.attempts ?? 0) + 1;
      try { await reserveRefreshAttempt(scope, original, now()); }
      catch { check(scope); /* Read back the reservation; never send without it. */ }
      record = await read(scope);
      if (!record.pending || record.pending.retryKey !== original.retryKey || record.pending.originalRefreshToken !== original.originalRefreshToken || record.pending.attempts !== intendedAttempt) throw new RefreshFailure('storage');
      check(scope);
      if (now() >= deadline) throw new RefreshFailure('reauthenticate');
      let response: SessionToken;
      try {
        response = await transport({ refresh_token: original.originalRefreshToken, retry_key: original.retryKey });
      } catch (error: any) {
        check(scope);
        if (error?.code === 'ERR_CANCELED') throw error;
        const status = error?.statusCode;
        const persistOutcome = async (outcome: { stopped?: boolean; retryAfterAt?: number }) => {
          try { await saveRefreshOutcome(scope, original, outcome); }
          catch { check(scope); throw new RefreshFailure('storage'); }
        };
        if (status === 401) { await persistOutcome({ stopped: true }); throw new RefreshFailure('reauthenticate', 401); }
        if (status === 409) {
          // No blind conflict retry. A future caller may join/reload its own durable successor.
          const detail = ['refresh_conflict', 'refresh_recovery_unavailable'].includes(error.detail) ? error.detail : undefined;
          await persistOutcome({ stopped: true });
          throw new RefreshFailure('reauthenticate', 409, detail);
        }
        if (status === 422) { await persistOutcome({ stopped: true }); throw new RefreshFailure('invalid-request', 422); }
        if (![0, 429, 503].includes(status)) throw new RefreshFailure('temporary', status);
        const delay = retryDelay(error.retryAfter, intendedAttempt, now());
        await persistOutcome({ retryAfterAt: Math.ceil(now() + delay / 1000) });
        if (intendedAttempt >= 3 || now() + delay / 1000 >= deadline) throw new RefreshFailure('temporary', status, undefined, error.retryAfter);
        await wait(delay, sessionSnapshot().signal); check(scope);
        continue;
      }
      check(scope);
      if (!response || response.session_id !== scope.sessionId || response.token_type !== 'bearer' ||
        typeof response.access_token !== 'string' || !response.access_token ||
        !Number.isSafeInteger(response.expires_in) || response.expires_in <= 0 ||
        original.preparedAt + response.expires_in <= now()) throw new RefreshFailure('invalid-response');
      const next: SavedSession = { version: 1, userId: scope.userId, sessionId: scope.sessionId,
        refreshToken: response.refresh_token, refreshExpiresAt: response.refresh_expires_at,
        sessionExpiresAt: response.session_expires_at, pending: null };
      try { await saveRefreshSuccessor(scope, original, next, now()); }
      catch { check(scope); /* A rejected native write may still have completed. */ }
      const persisted = await read(scope);
      if (persisted.pending || persisted.refreshToken !== next.refreshToken || persisted.refreshExpiresAt !== next.refreshExpiresAt ||
        persisted.sessionExpiresAt !== next.sessionExpiresAt) throw new RefreshFailure('storage');
      check(scope, persisted);
      if (original.preparedAt + response.expires_in <= now()) throw new RefreshFailure('invalid-response');
      setSessionToken(scope.generation, response.access_token, original.preparedAt + response.expires_in);
      return response;
    }
  }
  return function refresh(scope: SessionStorageScope): Promise<SessionToken> {
    try { check(scope); } catch (error) { return Promise.reject(error); }
    const identity = `${scope.userId}:${scope.sessionId}`;
    const existing = flights.get(scope.generation);
    if (existing) return existing.identity === identity ? existing.promise : Promise.reject(new RefreshFailure('reauthenticate'));
    const promise = run({ ...scope }).finally(() => { if (flights.get(scope.generation)?.promise === promise) flights.delete(scope.generation); });
    flights.set(scope.generation, { identity, promise });
    return promise;
  };
}

// Shared by automatic access handling; owns all bounded refresh recovery.
export const refreshSession = createRefreshCoordinator();
