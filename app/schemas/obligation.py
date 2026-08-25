from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ObligationStatus = Literal["active", "completed", "late", "defaulted"]
ObligationSource = Literal["manual_entry", "chatbot_entry"]


class ObligationCreate(BaseModel):
    provider: str = Field(..., min_length=1, max_length=120)
    item_name: str = Field(..., min_length=1, max_length=160)
    category: str = Field(..., min_length=1, max_length=80)
    total_amount: Decimal = Field(..., ge=Decimal("0.00"))
    monthly_installment_amount: Decimal = Field(..., ge=Decimal("0.00"))
    start_date: date
    term_months: int = Field(..., gt=0)
    due_day_of_month: int = Field(..., ge=1, le=31)
    status: ObligationStatus = "active"
    source: ObligationSource = "manual_entry"

    model_config = ConfigDict(extra="forbid")

class ObligationUpdate(BaseModel):
    provider: str | None = Field(default=None, min_length=1, max_length=120)
    item_name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    total_amount: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    monthly_installment_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
    )
    start_date: date | None = None
    term_months: int | None = Field(default=None, gt=0)
    due_day_of_month: int | None = Field(default=None, ge=1, le=31)
    status: ObligationStatus | None = None
    source: ObligationSource | None = None

    model_config = ConfigDict(extra="forbid")

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
