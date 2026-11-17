import { apiClient } from './client';
import type { SessionLogin, RefreshRequest, LogoutRequest, RevokeRequest, SessionToken, SessionSummary, SessionListParams } from '@/types/session';

// The active logout lifecycle uses isolated transport in logout.ts; management remains API-only.
export const sessionsApi = {
  async create(data: SessionLogin): Promise<SessionToken> {
    return (await apiClient.post<SessionToken>('/auth/sessions', data, { authMode: 'none' })).data;
  },
  async refresh(data: RefreshRequest): Promise<SessionToken> {
    return (await apiClient.post<SessionToken>('/auth/refresh', data, { authMode: 'none' })).data;
  },
  async logoutWithRefresh(data: LogoutRequest): Promise<void> {
    await apiClient.post('/auth/logout', data, { authMode: 'none' });
  },
  async logoutWithAccess(): Promise<void> {
    await apiClient.post('/auth/logout', undefined, { authMode: 'session' });
  },
  async list(params: SessionListParams = {}): Promise<SessionSummary[]> {
    return (await apiClient.get<SessionSummary[]>('/auth/sessions', { authMode: 'session', params })).data;
  },
  async revoke(sid: string, data: RevokeRequest): Promise<void> {
    await apiClient.post(`/auth/sessions/${encodeURIComponent(sid)}/revoke`, data, { authMode: 'session' });
  },
};
