from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DownPaymentProjectionResponse(BaseModel):
    obligation_id: int
    original_date: date
    amount: Decimal
    overdue: bool

    model_config = ConfigDict(from_attributes=True)


class ForecastMonthResponse(BaseModel):
    month: date
    income: Decimal
    fixed_expenses: Decimal
    obligation_payments: Decimal
    installment_payments: Decimal = Decimal("0.00")
    down_payment_payments: Decimal = Decimal("0.00")
    overdue_down_payment_payments: Decimal = Decimal("0.00")
    down_payment_details: list[DownPaymentProjectionResponse] = Field(default_factory=list)
    projected_buffer: Decimal
    has_negative_buffer: bool

    model_config = ConfigDict(from_attributes=True)


class ForecastResponse(BaseModel):
    rows: list[ForecastMonthResponse] = Field(default_factory=list)
