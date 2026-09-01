export interface ForecastMonthResponse {
  month: string;
  income: string;
  fixed_expenses: string;
  obligation_payments: string;
  projected_buffer: string;
  has_negative_buffer: boolean;
}

export interface ForecastResponse {
  rows: ForecastMonthResponse[];
}

export interface ForecastParams {
  start_month: string;
  months: number;
}
