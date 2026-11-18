import { apiClient } from './client';
import { validMoney, monetaryText } from '@/utils/financialValidation';
import { Token, UserCreate, UserLogin, UserResponse } from '@/types/auth';

export interface UserUpdate {
  monthly_income?: number | string;
  fixed_expenses?: number | string;
  currency?: string;
}

export const authApi = {
  async register(data: UserCreate): Promise<UserResponse> {
    const response = await apiClient.post<UserResponse>('/auth/register', data, { authMode: 'none' });
    return response.data;
  },

  async login(credentials: UserLogin): Promise<Token> {
    const response = await apiClient.post<Token>('/auth/login', credentials, { authMode: 'none' });
    return response.data;
  },

  async getMe(): Promise<UserResponse> {
    const response = await apiClient.get<UserResponse>('/auth/me');
    return response.data;
  },

  async updateMe(data: UserUpdate): Promise<UserResponse> {
    data = { ...data };
    for (const field of ['monthly_income', 'fixed_expenses'] as const) {
      const value = data[field];
      if (value !== undefined) {
        if (!validMoney(value)) throw new Error('Enter an amount from zero to 9,999,999,999.99, with at most two decimal places.');
        data[field] = typeof value === 'string' ? monetaryText(value) : value;
      }
    }
    const response = await apiClient.patch<UserResponse>('/auth/me', data);
    return response.data;
  },
};
