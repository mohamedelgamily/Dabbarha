export interface UserCreate {
  name: string;
  email: string;
  password: string;
  monthly_income?: number | string;
  fixed_expenses?: number | string;
  currency?: string;
}

export interface UserLogin {
  email: string;
  password: string;
}

export interface UserResponse {
  id: number;
  name: string;
  email: string;
  monthly_income: string | number;
  fixed_expenses: string | number;
  currency: string;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export interface AuthState {
  user: UserResponse | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
}
