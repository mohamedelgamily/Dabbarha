export type ObligationStatus = 'active' | 'completed' | 'late' | 'defaulted';
export type ObligationSource = 'manual_entry' | 'chatbot_entry';

export interface ObligationCreate {
  provider: string;
  item_name: string;
  category: string;
  total_amount: number | string;
  monthly_installment_amount: number | string;
  start_date: string; // ISO Date YYYY-MM-DD
  term_months: number;
  due_day_of_month: number;
  status?: ObligationStatus;
  source?: ObligationSource;
}

export interface ObligationUpdate {
  provider?: string;
  item_name?: string;
  category?: string;
  total_amount?: number | string;
  monthly_installment_amount?: number | string;
  start_date?: string;
  term_months?: number;
  due_day_of_month?: number;
  status?: ObligationStatus;
  source?: ObligationSource;
}

export interface ObligationResponse {
  id: number;
  user_id: number;
  provider: string;
  item_name: string;
  category: string;
  total_amount: string | number;
  monthly_installment_amount: string | number;
  start_date: string;
  term_months: number;
  due_day_of_month: number;
  status: ObligationStatus | string;
  source: ObligationSource | string;
  created_at: string;
  updated_at: string;
}
