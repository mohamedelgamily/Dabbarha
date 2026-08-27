from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AffordabilityRequest(BaseModel):
    amount: Decimal = Field(..., ge=Decimal("0.00"))
    start_date: date
    term_months: int = Field(..., gt=0)

    model_config = ConfigDict(extra="forbid")


class AffordabilityMonthResponse(BaseModel):
    month: date
    income: Decimal
    fixed_expenses: Decimal
    existing_obligation_payments: Decimal
    proposed_commitment_amount: Decimal
    projected_buffer: Decimal

    model_config = ConfigDict(from_attributes=True)


class AffordabilityResponse(BaseModel):
    classification: str
    worst_projected_buffer: Decimal
    worst_buffer_percentage: Decimal
    worst_month: date
    explanation: str
    monthly_results: list[AffordabilityMonthResponse] = Field(default_factory=list)
