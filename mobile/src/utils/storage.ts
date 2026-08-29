import * as SecureStore from 'expo-secure-store';
import { config } from '@/constants/config';
import { UserResponse } from '@/types/auth';

/**
 * Persists the JWT access token in encrypted device storage.
 */
export async function saveToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(config.tokenStorageKey, token);
}

/**
 * Retrieves the persisted JWT access token from encrypted device storage.
 */
export async function getToken(): Promise<string | null> {
  return await SecureStore.getItemAsync(config.tokenStorageKey);
}

/**
 * Deletes the persisted JWT access token from encrypted device storage.
 */
export async function deleteToken(): Promise<void> {
  await SecureStore.deleteItemAsync(config.tokenStorageKey);
}

/**
 * Persists cached user data.
 */
export async function saveUser(user: UserResponse): Promise<void> {
  await SecureStore.setItemAsync(config.userStorageKey, JSON.stringify(user));
}

/**
 * Retrieves cached user data.
 */
export async function getUser(): Promise<UserResponse | null> {
  const data = await SecureStore.getItemAsync(config.userStorageKey);
  if (!data) return null;
  try {
    return JSON.parse(data) as UserResponse;
  } catch {
    return null;
  }
}

/**
 * Deletes cached user data.
 */
export async function deleteUser(): Promise<void> {
  await SecureStore.deleteItemAsync(config.userStorageKey);
}

/**
 * Clears all authentication credentials and cached session data.
 */
export async function clearAuthStorage(): Promise<void> {
  await Promise.all([deleteToken(), deleteUser()]);
}
