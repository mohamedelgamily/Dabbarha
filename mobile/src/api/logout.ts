import axios from 'axios';
import { API_BASE_URL } from '@/constants/config';

// Deliberately isolated from account-bound interceptors: logout must survive
// local invalidation and must never borrow a newer account's bearer or refresh.
export const logoutClient = axios.create({ baseURL: API_BASE_URL, timeout: 10_000,
  headers: { 'Content-Type': 'application/json', Accept: 'application/json' } });
logoutClient.interceptors.request.use(request => {
  request.headers.delete('Authorization');
  request.auth = undefined;
  return request;
});

/** One bounded attempt; never propagate Axios errors containing credentials. */
export async function revokeLoggedOutSession(refreshToken: string): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await logoutClient.post('/auth/logout', { refresh_token: refreshToken }, { signal: controller.signal });
    return response.status === 204;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}
