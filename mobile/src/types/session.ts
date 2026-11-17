import type { UserLogin } from './auth';

export interface SessionLogin extends UserLogin { device_label?: string | null }
/** Credentials are canonical unpadded base64url encodings of 32 random bytes. */
export interface RefreshRequest { refresh_token: string; retry_key: string }
export interface LogoutRequest { refresh_token: string }
export interface RevokeRequest { password: string }
/** Absolute timestamps are UTC Unix seconds; expires_in is seconds. */
export interface SessionToken {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
  refresh_expires_at: number;
  session_id: string;
  session_expires_at: number;
}
export interface SessionSummary {
  id: string;
  device_label: string | null;
  created_at: number;
  last_refreshed_at: number;
  idle_expires_at: number;
  absolute_expires_at: number;
  revoked_at: number | null;
  current: boolean;
}
/** Backend bounds: offset 0–1,000,000; limit 1–100. Defaults: 0 and 50. */
export interface SessionListParams { offset?: number; limit?: number }
