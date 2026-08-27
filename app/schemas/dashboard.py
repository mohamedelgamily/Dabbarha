from decimal import Decimal

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    monthly_income: Decimal
    fixed_expenses: Decimal
    current_month_obligation_payments: Decimal
    current_month_projected_buffer: Decimal
    has_current_month_negative_buffer: bool
    active_obligations_count: int
