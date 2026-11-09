export type AffordabilityClassification =
  | 'Comfortable'
  | 'Manageable'
  | 'Risky'
  | 'Not Affordable';

export interface AffordabilityMonthResult {
  month: string;
  income: string;
  fixed_expenses: string;
  existing_obligation_payments: string;
  proposed_commitment_amount: string;
  proposed_installment_amount: string;
  proposed_down_payment_amount: string;
  projected_buffer: string;
}

export interface AffordabilityRequest {
  purchase_price: string;
  payment_method: 'manual' | 'automatic';
  interest_method: 'none' | 'flat' | 'reducing_balance';
  nominal_annual_interest_rate?: string;
  monthly_installment_amount?: string;
  start_date: string;
  term_months: number;
  due_day_of_month: number;
  down_payment_amount: string;
  down_payment_date?: string;
  down_payment_paid: boolean;
}

export interface AffordabilityResponse {
  classification: AffordabilityClassification;
  worst_projected_buffer: string;
  worst_buffer_percentage: string;
  worst_month: string;
  explanation: string;
  monthly_results: AffordabilityMonthResult[];
}
