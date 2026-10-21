from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.validation import Money, TermMonths, validate_calendar_window


class AffordabilityRequest(BaseModel):
    amount: Money
    start_date: date
    term_months: TermMonths

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def supported_calendar(self) -> "AffordabilityRequest":
        # The existing evaluator computes an exclusive end month.
        validate_calendar_window(self.start_date, self.term_months, exclusive_end=True)
        return self


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
