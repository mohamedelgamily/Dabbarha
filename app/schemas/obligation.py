from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.validation import DueDay, Money, TermMonths, TrimmedText, validate_calendar_window

ObligationStatus = Literal["active", "completed", "late", "defaulted"]
ObligationSource = Literal["manual_entry", "chatbot_entry"]


class ObligationCreate(BaseModel):
    provider: TrimmedText = Field(..., min_length=1, max_length=120)
    item_name: TrimmedText = Field(..., min_length=1, max_length=160)
    category: TrimmedText = Field(..., min_length=1, max_length=80)
    total_amount: Money
    monthly_installment_amount: Money
    start_date: date
    term_months: TermMonths
    due_day_of_month: DueDay
    status: ObligationStatus = "active"
    source: ObligationSource = "manual_entry"

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def supported_calendar(self) -> "ObligationCreate":
        validate_calendar_window(self.start_date, self.term_months)
        return self


class ObligationUpdate(BaseModel):
    provider: TrimmedText | None = Field(default=None, min_length=1, max_length=120)
    item_name: TrimmedText | None = Field(default=None, min_length=1, max_length=160)
    category: TrimmedText | None = Field(default=None, min_length=1, max_length=80)
    total_amount: Money | None = None
    monthly_installment_amount: Money | None = None
    start_date: date | None = None
    term_months: TermMonths | None = None
    due_day_of_month: DueDay | None = None
    status: ObligationStatus | None = None
    source: ObligationSource | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def reject_explicit_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Value cannot be null; omit the field to leave it unchanged.")
        return value


class ObligationResponse(BaseModel):
    id: int
    user_id: int
    provider: str
    item_name: str
    category: str
    total_amount: Decimal
    monthly_installment_amount: Decimal
    start_date: date
    term_months: int
    due_day_of_month: int
    status: str
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
