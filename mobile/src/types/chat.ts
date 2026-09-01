export interface ChatRequest {
  message: string;
  conversation_id?: number | null;
}

export interface ChatResponse {
  response: string;
  metadata: Record<string, string> | null;
  conversation_id: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export interface SendMessageParams {
  message: string;
  conversation_id?: number | null;
  confirmationToolKey?: string | null;
}

export type PendingConfirmation = {
  key: string;
  message: string;
  conversationId: number;
};

export type ToolExecutionStatus = 'executed' | 'error';
