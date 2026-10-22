"""Bounded request/response contracts for temporary financial support access."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.obligation import InstallmentResponse, ObligationResponse

SupportScope = Literal["financial_profile", "obligations", "installments", "payment_statuses"]
SupportReason = Literal["account_support", "payment_question", "security_review", "data_accuracy"]


class SupportGrantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_user_id: int = Field(gt=0, le=2147483647)
    support_case_reference: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{2,63}$")
    reason_code: SupportReason
    scopes: list[SupportScope] = Field(min_length=1, max_length=4)

    @field_validator("scopes")
    @classmethod
    def unique_scopes(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Scopes cannot be repeated.")
        return value


class SupportGrantApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    self_approval: bool = False


class SupportGrantResponse(BaseModel):
    grant_id: str
    target_user_id: int
    support_case_reference: str
    reason_code: SupportReason
    scopes: list[SupportScope]
    status: Literal["pending", "active", "revoked", "expired"]
    self_approved: bool
    requested_at: int
    approved_at: int | None
    expires_at: int
    revoked_at: int | None


class FinancialProfileSupportResponse(BaseModel):
    target_user_id: int
    monthly_income: Decimal
    fixed_expenses: Decimal
    currency: str


class SupportObligationPage(BaseModel):
    items: list[ObligationResponse]
    offset: int
    limit: int
    next_offset: int | None


class SupportInstallmentPage(BaseModel):
    obligation_id: int
    schedule_version: int
    items: list[InstallmentResponse]
    offset: int
    limit: int
    next_offset: int | None


class SupportPaymentStatus(BaseModel):
    occurrence_id: int
    obligation_id: int
    payment_kind: Literal["regular", "down_payment"]
    due_date: date
    scheduled_amount: Decimal
    state: Literal["unpaid", "paid", "superseded"]
    paid_at: datetime | None


class SupportPaymentStatusPage(BaseModel):
    items: list[SupportPaymentStatus]
    offset: int
    limit: int
    next_offset: int | None
