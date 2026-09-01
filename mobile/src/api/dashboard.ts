import { apiClient } from './client';
import { DashboardSummaryResponse } from '@/types/dashboard';

export const dashboardApi = {
  async getDashboardSummary(): Promise<DashboardSummaryResponse> {
    const response = await apiClient.get<DashboardSummaryResponse>('/dashboard/summary');
    return response.data;
  },
};
