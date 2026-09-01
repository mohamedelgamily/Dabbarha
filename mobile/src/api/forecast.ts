import { apiClient } from './client';
import { ForecastParams, ForecastResponse } from '@/types/forecast';

export const forecastApi = {
  async getForecast(params: ForecastParams): Promise<ForecastResponse> {
    const response = await apiClient.get<ForecastResponse>('/forecast', { params });
    return response.data;
  },
};
