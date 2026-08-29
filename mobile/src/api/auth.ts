import { apiClient } from './client';
import { Token, UserCreate, UserLogin, UserResponse } from '@/types/auth';

export const authApi = {
  /**
   * Register a new user
   */
  async register(data: UserCreate): Promise<UserResponse> {
    const response = await apiClient.post<UserResponse>('/auth/register', data);
    return response.data;
  },

  /**
   * Log in user with email and password, returning JWT access token
   */
  async login(credentials: UserLogin): Promise<Token> {
    const response = await apiClient.post<Token>('/auth/login', credentials);
    return response.data;
  },

  /**
   * Fetch profile for current authenticated user
   */
  async getMe(): Promise<UserResponse> {
    const response = await apiClient.get<UserResponse>('/auth/me');
    return response.data;
  },
};
