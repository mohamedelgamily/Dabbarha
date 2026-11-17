import { refreshSession, RefreshFailure } from './refreshCoordinator';
import { assertSession, onSessionAccess, sessionSnapshot, SessionAccessError } from './session';
import type { SessionStorageScope } from '@/utils/sessionStorage';

// Activated only after login/restoration has persisted and validated identity.
export function activateAutomaticRefresh(scope: SessionStorageScope, publish: (token: string) => void) {
  let required = false;
  let flight: Promise<void> | undefined;
  onSessionAccess(scope.generation, rejectedToken => {
    assertSession(scope.generation);
    if (flight) return flight;
    const current = sessionSnapshot();
    // A delayed 401 for a replaced token must not rotate the successor again.
    if (rejectedToken === current.token || (current.accessExpiresAt !== null &&
      current.accessExpiresAt <= Math.floor(Date.now() / 1000))) required = true;
    if (!required) return Promise.resolve();
    // The coordinator alone owns network retries and durable recovery. This gate
    // also covers publishing the new token and blocks sends after transient failure.
    flight = refreshSession(scope).then(response => {
      assertSession(scope.generation);
      publish(response.access_token);
      required = false;
    }).catch(error => {
      assertSession(scope.generation);
      if (error?.code === 'ERR_CANCELED') throw error;
      const terminal = error instanceof RefreshFailure &&
        ['reauthenticate', 'invalid-request', 'invalid-response'].includes(error.kind);
      if (terminal) {
        // Let the response interceptor clear the session. Aborting inside an
        // adapter would make Axios replace this useful error with cancellation.
        throw new SessionAccessError(401, 'Could not validate credentials', undefined, scope.generation, true);
      }
      throw new SessionAccessError(error?.statusCode ?? 503,
        error?.statusCode === 0 ? 'Unable to connect to the Dabbarha server. Please check your network.'
          : 'Your session could not be renewed. Please try again.', error?.retryAfter, scope.generation);
    }).finally(() => { flight = undefined; });
    return flight;
  });
}
