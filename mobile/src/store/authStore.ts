import { create } from 'zustand';
import { authApi, type UserUpdate } from '@/api/auth';
import { queryClient } from '@/api/queryClient';
import { sessionsApi } from '@/api/sessions';
import { activateAutomaticRefresh } from '@/api/automaticRefresh';
import { readSessionRecord, saveNewSession, clearStoredSessionForLogout } from '@/utils/sessionStorage';
import { revokeLoggedOutSession } from '@/api/logout';
import { refreshSession, RefreshFailure } from '@/api/refreshCoordinator';
import { UserCreate, UserLogin, UserResponse } from '@/types/auth';
import { clearAuthStorage, deleteToken, deleteUser, getToken, saveToken, saveUser, AuthStorageCleanupError, STORAGE_RECOVERY_MESSAGE, STORAGE_UNSAFE_MESSAGE } from '@/utils/storage';
import { assertSession, authStorageTask, onInvalidSession, resetPrivateSession, sessionSnapshot, setSessionToken } from '@/api/session';

interface AuthStoreState {
  user: UserResponse | null;
  token: string | null;
  sessionId: number;
  isAuthenticated: boolean;
  isLoading: boolean;
  isInitialized: boolean;
  restorationRetryable: boolean;
  logoutRevocation: 'idle' | 'pending' | 'confirmed' | 'unconfirmed' | 'local-only';
  error: string | null;
  initializeAuth: () => Promise<void>;
  dismissRestoration: () => void;
  login: (credentials: UserLogin) => Promise<void>;
  register: (data: UserCreate) => Promise<UserResponse>;
  logout: () => Promise<void>;
  clearError: () => void;
  updateProfile: (data: UserUpdate) => Promise<UserResponse>;
}

let pendingLoginGeneration: number | null = null;
let pendingRestorationGeneration: number | null = null;
class InvalidRestoration extends Error {}
let logoutFlight: { generation: number; promise: Promise<void> } | undefined;
export const LOGOUT_UNCONFIRMED_MESSAGE = 'You are signed out on this device, but server session revocation was not confirmed.';
const logoutRecoveryMessage = `${STORAGE_RECOVERY_MESSAGE} ${LOGOUT_UNCONFIRMED_MESSAGE}`;
const logoutUnsafeMessage = `${STORAGE_UNSAFE_MESSAGE} ${LOGOUT_UNCONFIRMED_MESSAGE}`;

function logoutSession(): Promise<void> {
  const previous = sessionSnapshot();
  if (logoutFlight?.generation === previous.generation) return logoutFlight.promise;
  const userId = useAuthStore.getState().user?.id;
  const mayHaveSession = previous.refreshable || pendingLoginGeneration === previous.generation ||
    pendingRestorationGeneration === previous.generation;
  const sessionId = resetPrivateSession();
  let finish!: () => void;
  const promise = new Promise<void>(resolve => { finish = resolve; });
  logoutFlight = { generation: sessionId, promise };
  useAuthStore.setState({ user: null, token: null, sessionId, isAuthenticated: false,
    isLoading: true, isInitialized: true, restorationRetryable: false, logoutRevocation: 'pending', error: null });
  void (async () => {
    const result = await clearStoredSessionForLogout(sessionId, userId);
    if (sessionId === sessionSnapshot().generation) {
      // Local sign-out and storage cleanup finish independently of the network.
      useAuthStore.setState({ isLoading: false, error: result.cleanupError });
    }
    let revocation: 'confirmed' | 'unconfirmed' | 'local-only';
    try {
      revocation = result.refreshToken
        ? await revokeLoggedOutSession(result.refreshToken) ? 'confirmed' : 'unconfirmed'
        : result.credentialUnavailable || mayHaveSession ? 'unconfirmed' : 'local-only';
    } finally {
      result.refreshToken = null; // No durable retry queue or credential retention.
    }
    if (sessionId !== sessionSnapshot().generation) return;
    const error = revocation !== 'unconfirmed' ? result.cleanupError
      : result.cleanupError === STORAGE_UNSAFE_MESSAGE ? logoutUnsafeMessage
      : result.cleanupError ? logoutRecoveryMessage : LOGOUT_UNCONFIRMED_MESSAGE;
    useAuthStore.setState({ logoutRevocation: revocation, error });
  })().catch(() => {
    if (sessionId === sessionSnapshot().generation) useAuthStore.setState({
      isLoading: false, logoutRevocation: 'unconfirmed', error: logoutUnsafeMessage });
  }).finally(finish);
  return promise;
}

// Reusable for account deletion later. Revoke memory access before awaiting storage.
export async function clearSession(): Promise<void> {
  const sessionId = resetPrivateSession();
  useAuthStore.setState({ user: null, token: null, sessionId, isAuthenticated: false,
    isLoading: true, isInitialized: true, restorationRetryable: false, logoutRevocation: 'idle', error: null });
  try {
    await authStorageTask(clearAuthStorage);
  } catch (error) {
    if (sessionId === sessionSnapshot().generation) useAuthStore.setState({ error: error instanceof AuthStorageCleanupError ? error.message : STORAGE_UNSAFE_MESSAGE });
  } finally {
    if (sessionId === sessionSnapshot().generation) useAuthStore.setState({ isLoading: false });
  }
}

async function persistIdentity(id: number, token: string, user: UserResponse) {
  await authStorageTask(async () => {
    assertSession(id);
    await saveToken(token);
    assertSession(id);
    await saveUser(user);
  });
  assertSession(id);
  useAuthStore.setState({ user, token, sessionId: id, isAuthenticated: true, isLoading: false, isInitialized: true, error: null });
}

export const useAuthStore = create<AuthStoreState>((set, get) => ({
  user: null, token: null, sessionId: 0, isAuthenticated: false,
  isLoading: false, isInitialized: false, restorationRetryable: false, logoutRevocation: 'idle', error: null,
  initializeAuth: async () => {
    if ((get().isInitialized && !get().restorationRetryable) || get().isLoading) return;
    const id = resetPrivateSession();
    pendingRestorationGeneration = id;
    set({ user: null, token: null, isAuthenticated: false, isInitialized: false,
      isLoading: true, sessionId: id, restorationRetryable: false, logoutRevocation: 'idle', error: null });
    try {
      const saved = await readSessionRecord(id);
      assertSession(id);
      if (saved.status !== 'missing') {
        // A present V2 record (including invalid/blocked records) always wins.
        if (saved.status !== 'ready' && saved.status !== 'pending') throw new InvalidRestoration();
        const record = saved.record;
        const scope = { generation: id, userId: record.userId, sessionId: record.sessionId };
        await authStorageTask(async () => {
          assertSession(id);
          // Remove obsolete legacy credentials without touching the V2 record.
          const results = await Promise.allSettled([deleteToken(), deleteUser()]);
          assertSession(id);
          if (results.some(result => result.status === 'rejected')) throw new Error('Storage unavailable');
        });
        assertSession(id);
        const response = await refreshSession(scope);
        assertSession(id);
        const user = await authApi.getMe();
        assertSession(id);
        if (user?.id !== record.userId || record.sessionExpiresAt <= Math.floor(Date.now() / 1000)) {
          throw new InvalidRestoration();
        }
        if ((sessionSnapshot().accessExpiresAt ?? 0) <= Math.floor(Date.now() / 1000)) {
          throw new Error('Access expired during restoration');
        }
        activateAutomaticRefresh(scope, token => { assertSession(id); set({ token }); });
        set({ user, token: response.access_token, isAuthenticated: true, isInitialized: true,
          isLoading: false, restorationRetryable: false, error: null });
        return;
      }
      const token = await authStorageTask(getToken);
      assertSession(id);
      if (!token) { set({ isLoading: false, isInitialized: true }); return; }
      setSessionToken(id, token);
      // Never render a cached identity before the server validates it.
      const user = await authApi.getMe();
      assertSession(id);
      await persistIdentity(id, token, user);
    } catch (error: any) {
      if (id !== sessionSnapshot().generation) return;
      const terminal = error instanceof InvalidRestoration || error?.statusCode === 401 ||
        (error instanceof RefreshFailure && ['reauthenticate', 'invalid-request', 'invalid-response'].includes(error.kind));
      if (terminal) {
        const cleanup = clearSession();
        const cleanupGeneration = sessionSnapshot().generation;
        await cleanup;
        if (cleanupGeneration === sessionSnapshot().generation && !get().error) set({ error: 'Could not validate credentials' });
      } else {
        // Drop provisional memory and private caches, but preserve durable
        // credentials/pending recovery across temporary network or storage faults.
        const sessionId = resetPrivateSession();
        set({ user: null, token: null, sessionId, isAuthenticated: false, isInitialized: true,
          isLoading: false, restorationRetryable: true,
          error: 'We could not restore your sign-in. Retry when your connection or device storage is available, or sign in again.' });
      }
    } finally {
      if (pendingRestorationGeneration === id) pendingRestorationGeneration = null;
    }
  },
  dismissRestoration: () => {
    if (get().restorationRetryable && !get().isLoading) set({ restorationRetryable: false, error: null });
  },
  login: async credentials => {
    if (get().isLoading && pendingRestorationGeneration !== sessionSnapshot().generation) return;
    const id = resetPrivateSession();
    pendingLoginGeneration = id;
    set({ user: null, token: null, sessionId: id, isAuthenticated: false, isLoading: true, restorationRetryable: false, logoutRevocation: 'idle', error: null });
    try {
      // Await earlier cleanup; do not carry a saved credential into a new login.
      await authStorageTask(clearAuthStorage);
      assertSession(id);
      const startedAt = Math.floor(Date.now() / 1000);
      const response = await sessionsApi.create({ email: credentials.email, password: credentials.password });
      assertSession(id);
      if (!response || response.token_type !== 'bearer' || typeof response.access_token !== 'string' ||
        !response.access_token || !Number.isSafeInteger(response.expires_in) || response.expires_in <= 0 ||
        startedAt + response.expires_in <= Math.floor(Date.now() / 1000)) {
        throw new Error('Dabbarha could not finish this request. Please try again.');
      }
      // Provisional transport credential for /me only; private navigation stays locked.
      setSessionToken(id, response.access_token, startedAt + response.expires_in);
      const user = await authApi.getMe();
      assertSession(id);
      try {
        // This operation owns the shared storage queue; never nest authStorageTask.
        await saveNewSession({ generation: id, userId: user.id, sessionId: response.session_id }, {
          version: 1, userId: user.id, sessionId: response.session_id,
          refreshToken: response.refresh_token, refreshExpiresAt: response.refresh_expires_at,
          sessionExpiresAt: response.session_expires_at, pending: null,
        });
      } catch {
        assertSession(id);
        throw new Error('Could not securely save your sign-in. Please try again.');
      }
      assertSession(id);
      if (startedAt + response.expires_in <= Math.floor(Date.now() / 1000)) {
        throw new Error('Dabbarha could not finish this request. Please try again.');
      }
      activateAutomaticRefresh({ generation: id, userId: user.id, sessionId: response.session_id }, token => {
        assertSession(id);
        set({ token });
      });
      set({ user, token: response.access_token, sessionId: id, isAuthenticated: true,
        isLoading: false, isInitialized: true, error: null });
    } catch (err: any) {
      if (id === sessionSnapshot().generation) {
        const cleanup = clearSession();
        const cleanupGeneration = sessionSnapshot().generation;
        await cleanup;
        // Cleanup can finish just as a new login starts; never publish an old error.
        if (cleanupGeneration === sessionSnapshot().generation && !get().error) {
          const message = err?.statusCode === 401 ? 'Invalid email or password'
            : err?.statusCode === 0 ? 'Unable to connect to the Dabbarha server. Please check your network.'
            : err?.message === 'Could not securely save your sign-in. Please try again.' ? err.message
            : 'Dabbarha could not finish this request. Please try again.';
          set({ error: message });
        }
      }
      throw err;
    } finally {
      if (pendingLoginGeneration === id) pendingLoginGeneration = null;
    }
  },
  register: async data => {
    const id = sessionSnapshot().generation;
    set({ isLoading: true, error: null });
    try {
      const user = await authApi.register(data);
      assertSession(id);
      set({ isLoading: false });
      return user;
    } catch (err: any) {
      if (id === sessionSnapshot().generation) set({ isLoading: false, error: err?.message || 'Registration failed. Please try again.' });
      throw err;
    }
  },
  logout: logoutSession,
  // Login's mount/input handlers must not dismiss unresolved storage recovery.
  clearError: () => {
    if (![STORAGE_RECOVERY_MESSAGE, STORAGE_UNSAFE_MESSAGE, LOGOUT_UNCONFIRMED_MESSAGE,
      logoutRecoveryMessage, logoutUnsafeMessage].includes(get().error || '')) set({ error: null });
  },
  updateProfile: async data => {
    const id = get().sessionId;
    if (!get().isAuthenticated) throw new Error('Not authenticated');
    set({ isLoading: true, error: null });
    try {
      const updated = await authApi.updateMe(data);
      assertSession(id);
      // The server response is authoritative; the cached profile is optional.
      set({ user: updated });
      void queryClient.invalidateQueries({ queryKey: ['dashboard-summary', id] }).catch(() => undefined);
      void queryClient.invalidateQueries({ queryKey: ['forecast', id] }).catch(() => undefined);
      try {
        await authStorageTask(async () => { assertSession(id); await saveUser(updated); });
      } catch {
        // Ignore only local profile-cache failure, never an ended session.
        assertSession(id);
      }
      assertSession(id);
      set({ isLoading: false });
      return updated;
    } catch (err: any) {
      if (id === sessionSnapshot().generation) set({ isLoading: false, error: err?.message || 'Failed to update profile. Please try again.' });
      throw err;
    }
  },
}));

onInvalidSession(() => {
  const failedLogin = pendingLoginGeneration === sessionSnapshot().generation ||
    pendingRestorationGeneration === sessionSnapshot().generation;
  const cleanup = clearSession();
  const cleanupGeneration = sessionSnapshot().generation;
  void cleanup.then(() => {
    // /me can reject a provisional login token. Keep the existing 401 cleanup,
    // but report this login failure only if no newer attempt has started.
    if (failedLogin && cleanupGeneration === sessionSnapshot().generation && !useAuthStore.getState().error) {
      useAuthStore.setState({ error: 'Could not validate credentials' });
    }
  });
});
