from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=1)
    monthly_income: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    fixed_expenses: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    currency: str = Field(default="EGP", min_length=1, max_length=3)


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    monthly_income: Decimal
    fixed_expenses: Decimal
    currency: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
