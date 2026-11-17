import { CanceledError } from 'axios';
import { queryClient } from './queryClient';

// Request lifetime only; authentication state continues to live in authStore.
let generation = 0;
let controller = new AbortController();
let accessToken: string | null = null;
let accessExpiresAt: number | null = null;
let accessHandler: ((rejectedToken?: string) => Promise<void>) | undefined;
let onInvalid: (() => void) | undefined;
let storageQueue: Promise<unknown> = Promise.resolve();

export function sessionSnapshot() {
  return { generation, signal: controller.signal, token: accessToken, accessExpiresAt, refreshable: !!accessHandler };
}
export function assertSession(expected: number) {
  if (expected !== generation) throw new CanceledError('Session ended');
}
// Bind work when its screen is rendered, not when an offline mutation resumes.
export function inSession<T, R>(expected: number, action: (value: T) => Promise<R>) {
  return async (value: T): Promise<R> => {
    assertSession(expected);
    const result = await action(value);
    assertSession(expected);
    return result;
  };
}
export function setSessionToken(expected: number, token: string, expiresAt: number | null = null) {
  assertSession(expected);
  accessToken = token;
  accessExpiresAt = expiresAt;
}
export function onSessionAccess(expected: number, handler: (rejectedToken?: string) => Promise<void>) {
  assertSession(expected);
  accessHandler = handler;
}
export async function ensureSessionAccess(expected: number, rejectedToken?: string) {
  assertSession(expected);
  await accessHandler?.(rejectedToken);
  assertSession(expected);
}
export class SessionAccessError extends Error {
  constructor(public readonly statusCode: number, message: string, public readonly retryAfter?: string,
    public readonly generation?: number, public readonly terminal = false) { super(message); }
}
export function onInvalidSession(handler: () => void) { onInvalid = handler; }
export function invalidateSession(expected: number) {
  if (expected === generation) onInvalid?.();
}
export function resetPrivateSession() {
  generation += 1;
  accessToken = null;
  accessExpiresAt = null;
  accessHandler = undefined;
  controller.abort();
  controller = new AbortController();
  // Cancellation is initiated synchronously; clear mutations as well as queries.
  void queryClient.cancelQueries().catch(() => undefined);
  queryClient.clear();
  return generation;
}
// Serialize credential writes and deletion so a late write cannot undo logout.
export function authStorageTask<T>(task: () => Promise<T>): Promise<T> {
  const result = storageQueue.then(task);
  storageQueue = result.catch(() => undefined);
  return result;
}
