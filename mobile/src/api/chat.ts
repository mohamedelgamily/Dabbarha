import { apiClient } from './client';
import { ChatRequest, ChatResponse } from '@/types/chat';

export const chatApi = {
  async sendMessage(request: ChatRequest): Promise<ChatResponse> {
    const response = await apiClient.post<ChatResponse>('/chat', request);
    return response.data;
  },
};
