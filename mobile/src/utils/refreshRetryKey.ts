import { getRandomBytesAsync } from 'expo-crypto';

export async function generateRefreshRetryKey(): Promise<string> {
  // Async Expo API has no Math.random development fallback. Fail closed.
  const bytes = await getRandomBytesAsync(32);
  if (bytes.length !== 32) throw new Error('Secure randomness unavailable');
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  let result = '', buffer = 0, bits = 0;
  for (const byte of bytes) {
    buffer = (buffer << 8) | byte; bits += 8;
    while (bits >= 6) { bits -= 6; result += alphabet[(buffer >>> bits) & 63]; }
  }
  if (bits) result += alphabet[(buffer << (6 - bits)) & 63];
  return result;
}
