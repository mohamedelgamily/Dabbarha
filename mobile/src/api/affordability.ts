import { apiClient } from './client';
import { AffordabilityRequest, AffordabilityResponse } from '@/types/affordability';
import { en } from '@/i18n/dictionaries';

// Only known application messages are safe to display as backend errors.
// Never apply this mapping to user content or change global translation behavior.
export function affordabilityErrorMessage(message: unknown): string {
  const value = typeof message === 'string' ? message : '';
  const key = value.startsWith('Value error, ') ? value.slice(13) : value;
  return Object.prototype.hasOwnProperty.call(en, key) ? key
    : 'We could not evaluate this payment plan. Check your entries and try again.';
}

export const affordabilityApi = {
  async evaluateAffordability(
    data: AffordabilityRequest,
  ): Promise<AffordabilityResponse> {
    try {
      const response = await apiClient.post<AffordabilityResponse>('/affordability', data);
      return response.data;
    } catch (error: any) {
      if (error?.code === 'ERR_CANCELED') throw error;
      throw {
        statusCode: error?.statusCode,
        message: affordabilityErrorMessage(error?.message),
        detail: Array.isArray(error?.detail)
          ? error.detail.map((issue: any) => ({ loc: issue.loc, type: issue.type, msg: affordabilityErrorMessage(issue.msg) }))
          : undefined,
      };
    }
  },
};
