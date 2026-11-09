import { create } from 'zustand';
import { authApi, type UserUpdate } from '@/api/auth';
import { UserCreate, UserLogin, UserResponse } from '@/types/auth';
import { clearAuthStorage, getToken, saveToken, saveUser, AuthStorageCleanupError, STORAGE_RECOVERY_MESSAGE, STORAGE_UNSAFE_MESSAGE } from '@/utils/storage';
import { assertSession, authStorageTask, onInvalidSession, resetPrivateSession, sessionSnapshot, setSessionToken } from '@/api/session';

interface AuthStoreState {
  user: UserResponse | null;
  token: string | null;
  sessionId: number;
  isAuthenticated: boolean;
  isLoading: boolean;
  isInitialized: boolean;
  error: string | null;
  initializeAuth: () => Promise<void>;
  login: (credentials: UserLogin) => Promise<void>;
  register: (data: UserCreate) => Promise<UserResponse>;
  logout: () => Promise<void>;
  clearError: () => void;
  updateProfile: (data: UserUpdate) => Promise<UserResponse>;
}

// Reusable for account deletion later. Revoke memory access before awaiting storage.
export async function clearSession(): Promise<void> {
  const sessionId = resetPrivateSession();
  useAuthStore.setState({ user: null, token: null, sessionId, isAuthenticated: false,
    isLoading: true, isInitialized: true, error: null });
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
  isLoading: false, isInitialized: false, error: null,
  initializeAuth: async () => {
    if (get().isInitialized || get().isLoading) return;
    const id = resetPrivateSession();
    set({ isLoading: true, sessionId: id });
    try {
      const token = await authStorageTask(getToken);
      assertSession(id);
      if (!token) { set({ isLoading: false, isInitialized: true }); return; }
      setSessionToken(id, token);
      // Never render a cached identity before the server validates it.
      const user = await authApi.getMe();
      assertSession(id);
      await persistIdentity(id, token, user);
    } catch {
      if (id === sessionSnapshot().generation) await clearSession();
    }
  },
  login: async credentials => {
    if (get().isLoading) return;
    const id = resetPrivateSession();
    set({ user: null, token: null, sessionId: id, isAuthenticated: false, isLoading: true, error: null });
    try {
      // Await earlier cleanup; do not carry a saved credential into a new login.
      await authStorageTask(clearAuthStorage);
      assertSession(id);
      const response = await authApi.login(credentials);
      assertSession(id);
      setSessionToken(id, response.access_token);
      const user = await authApi.getMe();
      assertSession(id);
      await persistIdentity(id, response.access_token, user);
    } catch (err: any) {
      if (id === sessionSnapshot().generation) {
        await clearSession();
        if (!get().error) set({ error: err?.message || 'Login failed. Please check your credentials.' });
      }
      throw err;
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
  logout: clearSession,
  // Login's mount/input handlers must not dismiss unresolved storage recovery.
  clearError: () => {
    if (![STORAGE_RECOVERY_MESSAGE, STORAGE_UNSAFE_MESSAGE].includes(get().error || '')) set({ error: null });
  },
  updateProfile: async data => {
    const id = get().sessionId;
    if (!get().isAuthenticated) throw new Error('Not authenticated');
    set({ isLoading: true, error: null });
    try {
      const updated = await authApi.updateMe(data);
      assertSession(id);
      await authStorageTask(async () => { assertSession(id); await saveUser(updated); });
      assertSession(id);
      set({ user: updated, isLoading: false });
      return updated;
    } catch (err: any) {
      if (id === sessionSnapshot().generation) set({ isLoading: false, error: err?.message || 'Failed to update profile. Please try again.' });
      throw err;
    }
  },
}));

onInvalidSession(() => { void clearSession(); });
