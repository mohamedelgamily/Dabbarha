import { Platform } from 'react-native';

const getDefaultApiUrl = (): string => {
  // If explicitly configured via environment variable, use it
  if (process.env.EXPO_PUBLIC_API_URL) {
    return process.env.EXPO_PUBLIC_API_URL;
  }

  // Fallback defaults for local development
  if (Platform.OS === 'android') {
    // Android emulator connects to host machine via 10.0.2.2
    return 'http://10.0.2.2:8000';
  }

  // iOS simulator connects to host machine via localhost
  return 'http://localhost:8000';
};

export const API_BASE_URL = getDefaultApiUrl();

export const config = {
  apiBaseUrl: API_BASE_URL,
  apiTimeoutMs: 15000,
  tokenStorageKey: 'dabbarha_access_token',
  userStorageKey: 'dabbarha_user_data',
} as const;
