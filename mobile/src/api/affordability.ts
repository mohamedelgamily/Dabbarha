import { apiClient } from './client';
import { AffordabilityRequest, AffordabilityResponse } from '@/types/affordability';

export const affordabilityApi = {
  async evaluateAffordability(
    data: AffordabilityRequest,
  ): Promise<AffordabilityResponse> {
    const response = await apiClient.post<AffordabilityResponse>('/affordability', {
      amount: Number(data.amount),
      start_date: data.start_date,
      term_months: Number(data.term_months),
    });
    return response.data;
  },
};
