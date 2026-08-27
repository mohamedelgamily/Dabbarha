from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ForecastMonthResponse(BaseModel):
    month: date
    income: Decimal
    fixed_expenses: Decimal
    obligation_payments: Decimal
    projected_buffer: Decimal
    has_negative_buffer: bool

    model_config = ConfigDict(from_attributes=True)


class ForecastResponse(BaseModel):
    rows: list[ForecastMonthResponse] = Field(default_factory=list)
