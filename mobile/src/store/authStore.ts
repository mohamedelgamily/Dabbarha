import { create } from 'zustand';
import { authApi } from '@/api/auth';
import { UserCreate, UserLogin, UserResponse } from '@/types/auth';
import {
  clearAuthStorage,
  getToken,
  getUser,
  saveToken,
  saveUser,
} from '@/utils/storage';

interface AuthStoreState {
  user: UserResponse | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isInitialized: boolean;
  error: string | null;

  initializeAuth: () => Promise<void>;
  login: (credentials: UserLogin) => Promise<void>;
  register: (data: UserCreate) => Promise<UserResponse>;
  logout: () => Promise<void>;
  setUser: (user: UserResponse | null) => void;
  clearError: () => void;
}

export const useAuthStore = create<AuthStoreState>((set, get) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: false,
  isInitialized: false,
  error: null,

  initializeAuth: async () => {
    try {
      set({ isLoading: true });
      const token = await getToken();

      if (!token) {
        set({
          token: null,
          user: null,
          isAuthenticated: false,
          isLoading: false,
          isInitialized: true,
        });
        return;
      }

      // First check local cache for immediate render
      const cachedUser = await getUser();
      if (cachedUser) {
        set({
          token,
          user: cachedUser,
          isAuthenticated: true,
        });
      }

      // Validate with server
      const user = await authApi.getMe();
      await saveUser(user);
      set({
        token,
        user,
        isAuthenticated: true,
        isLoading: false,
        isInitialized: true,
      });
    } catch {
      // Token is expired or invalid
      await clearAuthStorage();
      set({
        token: null,
        user: null,
        isAuthenticated: false,
        isLoading: false,
        isInitialized: true,
      });
    }
  },

  login: async (credentials: UserLogin) => {
    try {
      set({ isLoading: true, error: null });
      const tokenResponse = await authApi.login(credentials);
      await saveToken(tokenResponse.access_token);

      // Fetch user profile with the new token
      const user = await authApi.getMe();
      await saveUser(user);

      set({
        token: tokenResponse.access_token,
        user,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } catch (err: any) {
      await clearAuthStorage();
      const message = err?.message || 'Login failed. Please check your credentials.';
      set({
        token: null,
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: message,
      });
      throw err;
    }
  },

  register: async (data: UserCreate) => {
    try {
      set({ isLoading: true, error: null });
      const user = await authApi.register(data);
      set({ isLoading: false, error: null });
      return user;
    } catch (err: any) {
      const message = err?.message || 'Registration failed. Please try again.';
      set({ isLoading: false, error: message });
      throw err;
    }
  },

  logout: async () => {
    try {
      set({ isLoading: true });
      await clearAuthStorage();
    } finally {
      set({
        token: null,
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
      });
    }
  },

  setUser: (user: UserResponse | null) => {
    set({ user, isAuthenticated: !!user });
  },

  clearError: () => {
    set({ error: null });
  },
}));
