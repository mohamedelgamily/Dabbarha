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
  projected_buffer: string;
}

export interface AffordabilityRequest {
  amount: string;
  start_date: string;
  term_months: string;
}

export interface AffordabilityResponse {
  classification: AffordabilityClassification;
  worst_projected_buffer: string;
  worst_buffer_percentage: string;
  worst_month: string;
  explanation: string;
  monthly_results: AffordabilityMonthResult[];
}
