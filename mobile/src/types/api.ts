export interface ApiErrorDetail {
  loc?: (string | number)[];
  msg: string;
  type?: string;
}

export interface ApiErrorResponse {
  detail?: string | ApiErrorDetail[];
  message?: string;
  statusCode?: number;
  /** Raw Retry-After value; no retry policy is applied by the transport. */
  retryAfter?: string;
}
