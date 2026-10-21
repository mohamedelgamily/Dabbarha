from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.forecast import DownPaymentProjectionResponse


class DashboardSummaryResponse(BaseModel):
    monthly_income: Decimal
    fixed_expenses: Decimal
    current_month_obligation_payments: Decimal
    current_month_installment_payments: Decimal = Decimal("0.00")
    current_month_down_payment_payments: Decimal = Decimal("0.00")
    current_month_overdue_down_payment_payments: Decimal = Decimal("0.00")
    current_month_down_payment_details: list[DownPaymentProjectionResponse] = Field(default_factory=list)
    current_month_projected_buffer: Decimal
    has_current_month_negative_buffer: bool
    active_obligations_count: int
