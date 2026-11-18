import { apiClient } from './client';
import { validMoney, monetaryText, validDate, validTerm, validObligationCalendar } from '@/utils/financialValidation';
import {
  ObligationCreate,
  ObligationResponse,
  ObligationUpdate,
} from '@/types/obligation';

function validatePayload(data: ObligationUpdate, creating = false): ObligationUpdate {
  const payload = { ...data };
  for (const field of ['total_amount', 'monthly_installment_amount'] as const) {
    const value = payload[field];
    if (value !== undefined || creating) {
      if (!validMoney(value)) throw new Error('Enter an amount from zero to 9,999,999,999.99, with at most two decimal places.');
      payload[field] = typeof value === 'string' ? monetaryText(value) : value;
    }
  }
  if ((data.start_date !== undefined || creating) && (typeof data.start_date !== 'string' || !validDate(data.start_date))) throw new Error('Enter a real date in YYYY-MM-DD format.');
  if ((data.term_months !== undefined || creating) && !validTerm(data.term_months)) throw new Error('Choose a whole number from 1 to 1,200 months.');
  if (data.start_date !== undefined && data.term_months !== undefined && !validObligationCalendar(data.start_date, data.term_months)) throw new Error('This payment period is outside the supported calendar.');
  return payload;
}

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
    const response = await apiClient.post<ObligationResponse>('/obligations', validatePayload(data, true));
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
      validatePayload(data)
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
