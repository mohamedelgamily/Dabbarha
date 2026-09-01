import { apiClient } from './client';
import { ChatResponse, SendMessageParams } from '@/types/chat';

export const chatApi = {
  async sendMessage(params: SendMessageParams): Promise<ChatResponse> {
    const headers: Record<string, string> = {};
    if (params.confirmationToolKey) {
      headers['X-Confirmed-Tool-Key'] = params.confirmationToolKey;
    }

    const response = await apiClient.post<ChatResponse>(
      '/chat',
      {
        message: params.message,
        conversation_id: params.conversation_id,
      },
      { headers },
    );
    return response.data;
  },
};
