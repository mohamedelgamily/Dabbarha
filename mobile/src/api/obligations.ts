import { apiClient } from './client';
import {
  ObligationCreate,
  ObligationResponse,
  ObligationUpdate,
} from '@/types/obligation';

export const obligationsApi = {
  /**
   * List all obligations belonging to the authenticated user
   */
  async getObligations(): Promise<ObligationResponse[]> {
    const response = await apiClient.get<ObligationResponse[]>('/obligations');
    return response.data;
  },

  /**
   * Retrieve a specific obligation by ID
   */
  async getObligationById(id: number): Promise<ObligationResponse> {
    const response = await apiClient.get<ObligationResponse>(`/obligations/${id}`);
    return response.data;
  },

  /**
   * Create a new financial obligation
   */
  async createObligation(data: ObligationCreate): Promise<ObligationResponse> {
    const response = await apiClient.post<ObligationResponse>('/obligations', data);
    return response.data;
  },

  /**
   * Update an existing obligation
   */
  async updateObligation(
    id: number,
    data: ObligationUpdate
  ): Promise<ObligationResponse> {
    const response = await apiClient.put<ObligationResponse>(
      `/obligations/${id}`,
      data
    );
    return response.data;
  },

  /**
   * Delete an obligation by ID
   */
  async deleteObligation(id: number): Promise<void> {
    await apiClient.delete(`/obligations/${id}`);
  },
};
