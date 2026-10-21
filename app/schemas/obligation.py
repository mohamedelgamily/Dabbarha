from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

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
    purchase_price: Decimal | None = None
    payment_method: str | None = None
    interest_method: str | None = None
    nominal_annual_interest_rate: Decimal | None = None
    down_payment_amount: Decimal = Decimal("0.00")
    down_payment_date: date | None = None
    down_payment_paid: bool = False
    schedule_version: int = 0
    start_date: date
    term_months: int
    due_day_of_month: int
    status: str
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InstallmentPlanCreate(BaseModel):
    provider: TrimmedText = Field(..., min_length=1, max_length=120)
    item_name: TrimmedText = Field(..., min_length=1, max_length=160)
    category: TrimmedText = Field(..., min_length=1, max_length=80)
    purchase_price: Money
    payment_method: Literal["manual", "automatic"]
    interest_method: Literal["none", "flat", "reducing_balance"] = "none"
    nominal_annual_interest_rate: Annotated[
        Decimal, Field(ge=0, le=100, max_digits=7, decimal_places=4, allow_inf_nan=False)
    ] | None = None
    monthly_installment_amount: Money | None = None
    down_payment_amount: Money = Decimal("0.00")
    down_payment_date: date | None = None
    down_payment_paid: bool = False
    start_date: date
    term_months: TermMonths
    due_day_of_month: DueDay
    status: ObligationStatus = "active"

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_plan(self) -> "InstallmentPlanCreate":
        validate_calendar_window(self.start_date, self.term_months)
        if self.down_payment_amount >= self.purchase_price:
            raise ValueError("Down payment must be less than the purchase price.")
        if self.down_payment_amount == 0:
            if self.down_payment_date is not None or self.down_payment_paid:
                raise ValueError("A down-payment date or paid status requires a positive amount.")
        elif self.down_payment_date is None:
            raise ValueError("Enter the exact date for the down payment.")
        if self.down_payment_paid and self.down_payment_date is None:
            raise ValueError("A paid down payment must have a date.")
        if self.payment_method == "manual" and self.monthly_installment_amount is None:
            raise ValueError("Enter the provider's actual monthly installment.")
        if self.payment_method == "automatic" and self.monthly_installment_amount is not None:
            raise ValueError("Leave monthly_installment_amount empty for automatic calculations.")
        if self.payment_method == "automatic" and self.interest_method == "none" and self.nominal_annual_interest_rate not in (None, Decimal("0")):
            raise ValueError("No-interest plans must use a 0% annual rate.")
        return self


class InstallmentPlanUpdate(InstallmentPlanCreate):
    schedule_version: int = Field(ge=0)
    status: ObligationStatus | None = None


class InstallmentPlanConversion(InstallmentPlanCreate):
    confirm_conversion: Literal[True]
    status: ObligationStatus | None = None


class InstallmentResponse(BaseModel):
    installment_number: int
    due_date: date
    scheduled_amount: Decimal
    principal_amount: Decimal | None
    interest_amount: Decimal | None

    model_config = ConfigDict(from_attributes=True)


class InstallmentScheduleResponse(BaseModel):
    obligation_id: int
    schedule_version: int
    installments: list[InstallmentResponse]
