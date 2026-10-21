from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.validation import DueDay, Money, TermMonths, validate_calendar_window


class AffordabilityRequest(BaseModel):
    amount: Money | None = None
    start_date: date
    term_months: TermMonths
    purchase_price: Money | None = None
    payment_method: Literal["manual", "automatic"] | None = None
    interest_method: Literal["none", "flat", "reducing_balance"] = "none"
    nominal_annual_interest_rate: Annotated[
        Decimal, Field(ge=0, le=100, max_digits=7, decimal_places=4, allow_inf_nan=False)
    ] | None = None
    monthly_installment_amount: Money | None = None
    down_payment_amount: Money = Decimal("0.00")
    down_payment_date: date | None = None
    down_payment_paid: bool = False
    due_day_of_month: DueDay = 1

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def supported_calendar(self) -> "AffordabilityRequest":
        if self.purchase_price is None:
            if self.amount is None:
                raise ValueError("Enter a monthly amount or a purchase price and payment method.")
            if any((self.payment_method is not None, self.monthly_installment_amount is not None,
                    self.down_payment_amount != 0, self.down_payment_date is not None, self.down_payment_paid)):
                raise ValueError("Installment plan fields require purchase_price.")
        else:
            if self.payment_method is None:
                raise ValueError("Choose a payment method for a purchase-price affordability assessment.")
            if self.down_payment_amount >= self.purchase_price:
                raise ValueError("Down payment must be less than the purchase price.")
            if self.down_payment_amount == 0 and (self.down_payment_date is not None or self.down_payment_paid):
                raise ValueError("A down-payment date or paid status requires a positive amount.")
            if self.down_payment_amount > 0 and self.down_payment_date is None:
                raise ValueError("Enter the exact date for the down payment.")
            if self.payment_method == "manual":
                if self.amount is None and self.monthly_installment_amount is None:
                    raise ValueError("Enter the provider's actual monthly installment.")
                if self.amount is not None and self.monthly_installment_amount is not None:
                    raise ValueError("Send the monthly installment in only one field.")
            elif self.amount is not None or self.monthly_installment_amount is not None:
                raise ValueError("Automatic calculations do not accept a manual monthly amount.")
            if self.payment_method == "automatic" and self.interest_method == "none" and self.nominal_annual_interest_rate not in (None, Decimal("0")):
                raise ValueError("No-interest plans must use a 0% annual rate.")
        # The existing evaluator computes an exclusive end month.
        validate_calendar_window(self.start_date, self.term_months, exclusive_end=True)
        if self.down_payment_date is not None:
            validate_calendar_window(self.down_payment_date, 1)
        return self


class AffordabilityMonthResponse(BaseModel):
    month: date
    income: Decimal
    fixed_expenses: Decimal
    existing_obligation_payments: Decimal
    proposed_commitment_amount: Decimal
    proposed_installment_amount: Decimal = Decimal("0.00")
    proposed_down_payment_amount: Decimal = Decimal("0.00")
    projected_buffer: Decimal

    model_config = ConfigDict(from_attributes=True)


class AffordabilityResponse(BaseModel):
    classification: str
    worst_projected_buffer: Decimal
    worst_buffer_percentage: Decimal
    worst_month: date
    explanation: str
    monthly_results: list[AffordabilityMonthResponse] = Field(default_factory=list)
