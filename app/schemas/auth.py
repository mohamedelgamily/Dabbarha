from datetime import datetime
from decimal import Decimal

from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.validation import Money, TrimmedText


class UserCreate(BaseModel):
    # Financial information (monthly_income, fixed_expenses, currency) is intentionally
    # NOT part of registration. Users can provide/update it later via PATCH /auth/me.
    # Defaults on the User model (income=0, expenses=0, currency="EGP") apply on register.
    model_config = ConfigDict(extra="forbid")

    name: TrimmedText = Field(..., min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_registration_password(cls, value: str) -> str:
        if not value.strip() or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("Password must contain non-whitespace text and valid Unicode.")
        return value


class UserUpdate(BaseModel):
    """Partial update schema for the authenticated user's profile.

    Only financial-profile fields are updatable here. Identity fields
    (name, email, password) and immutable fields (id, created_at) are
    intentionally excluded and rejected via ``extra="forbid"``.
    """

    model_config = ConfigDict(extra="forbid")

    monthly_income: Money | None = None
    fixed_expenses: Money | None = None
    currency: str | None = Field(default=None, min_length=1, max_length=3)

    @field_validator("monthly_income", "fixed_expenses", mode="before")
    @classmethod
    def validate_non_null_numeric(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("Value cannot be null.")
        return v

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("Currency cannot be null.")
        if not isinstance(v, str):
            raise ValueError("Currency must be a string.")
        v = v.strip().upper()
        if not v:
            raise ValueError("Currency cannot be empty or whitespace.")
        return v


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    monthly_income: Decimal
    fixed_expenses: Decimal
    currency: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)

    @field_validator("password")
    @classmethod
    def validate_login_unicode(cls, value: str) -> str:
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("Password must contain valid Unicode.")
        return value


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
