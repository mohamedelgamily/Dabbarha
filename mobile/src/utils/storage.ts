import * as SecureStore from 'expo-secure-store';
import { config } from '@/constants/config';
import { UserResponse } from '@/types/auth';

export const logoutMarkerKey = `${config.tokenStorageKey}_logout_pending`;
export const v2SessionStorageKey = 'dabbarha_session_v2';
export const STORAGE_RECOVERY_MESSAGE = 'Saved sign-in could not be cleared. Try signing in again to retry cleanup. If this continues, clear the app data before using a shared device.';
export const STORAGE_UNSAFE_MESSAGE = 'Saved sign-in could not be cleared or blocked from restoration. Clear the app data before reopening it on a shared device, or try signing in again to retry cleanup.';
export class AuthStorageCleanupError extends Error {}

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
  // A durable logout intent takes precedence over any leftover credential.
  if (await SecureStore.getItemAsync(logoutMarkerKey)) {
    await clearAuthStorage();
    return null;
  }
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
  let blocked = false;
  try {
    await SecureStore.setItemAsync(logoutMarkerKey, '1');
    blocked = true;
  } catch {
    // Still attempt deletion when storage cannot persist the logout intent.
  }
  // Wait for both deletions even if one fails, before a later session may write.
  const results = await Promise.allSettled([deleteToken(), deleteUser(), SecureStore.deleteItemAsync(v2SessionStorageKey)]);
  const failed = results.find((result) => result.status === 'rejected');
  if (failed) {
    if (!blocked) {
      try {
        // Independent fallback if writing the marker failed but replacement works.
        const replacements = await Promise.allSettled([
          SecureStore.setItemAsync(config.tokenStorageKey, ''),
          SecureStore.setItemAsync(v2SessionStorageKey, ''),
        ]);
        // Each credential must either have been deleted or replaced successfully.
        blocked = (results[0].status === 'fulfilled' || replacements[0].status === 'fulfilled') &&
          (results[2].status === 'fulfilled' || replacements[1].status === 'fulfilled');
      } catch { /* No durable guarantee is possible if all writes fail. */ }
    }
    throw new AuthStorageCleanupError(blocked ? STORAGE_RECOVERY_MESSAGE : STORAGE_UNSAFE_MESSAGE);
  }
  try {
    await SecureStore.deleteItemAsync(logoutMarkerKey);
  } catch {
    throw new AuthStorageCleanupError(STORAGE_RECOVERY_MESSAGE);
  }
}
