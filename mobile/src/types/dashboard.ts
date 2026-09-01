export interface DashboardSummaryResponse {
  monthly_income: string;
  fixed_expenses: string;
  current_month_obligation_payments: string;
  current_month_projected_buffer: string;
  has_current_month_negative_buffer: boolean;
  active_obligations_count: number;
}
