import { apiClient } from './client';
import { Token, UserCreate, UserLogin, UserResponse } from '@/types/auth';

export interface UserUpdate {
  monthly_income?: number | string;
  fixed_expenses?: number | string;
  currency?: string;
}

export const authApi = {
  async register(data: UserCreate): Promise<UserResponse> {
    const response = await apiClient.post<UserResponse>('/auth/register', data);
    return response.data;
  },

  async login(credentials: UserLogin): Promise<Token> {
    const response = await apiClient.post<Token>('/auth/login', credentials);
    return response.data;
  },

  async getMe(): Promise<UserResponse> {
    const response = await apiClient.get<UserResponse>('/auth/me');
    return response.data;
  },

  async updateMe(data: UserUpdate): Promise<UserResponse> {
    const response = await apiClient.patch<UserResponse>('/auth/me', data);
    return response.data;
  },
};
