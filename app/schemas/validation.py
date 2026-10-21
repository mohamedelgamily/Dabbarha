"""Shared request limits; response schemas intentionally retain legacy read compatibility."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BeforeValidator, Field

MAX_TERM_MONTHS = 1200
MAX_FORECAST_MONTHS = 60
MAX_MONEY = Decimal("9999999999.99")


def reject_boolean(value: Any) -> Any:
    if isinstance(value, bool):
        raise ValueError("A numeric value is required; true/false is not accepted.")
    return value


def trim_text(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


Money = Annotated[
    Decimal,
    Field(ge=0, le=MAX_MONEY, max_digits=12, decimal_places=2, allow_inf_nan=False),
    BeforeValidator(reject_boolean),
]
TermMonths = Annotated[int, Field(ge=1, le=MAX_TERM_MONTHS), BeforeValidator(reject_boolean)]
DueDay = Annotated[int, Field(ge=1, le=31), BeforeValidator(reject_boolean)]
TrimmedText = Annotated[str, BeforeValidator(trim_text)]


def validate_calendar_window(start: date, months: int, *, exclusive_end: bool = False) -> None:
    # Compare month indices before doing any date arithmetic. Day-of-month is
    # intentionally irrelevant: the financial engine operates on calendar months.
    last_index = start.year * 12 + start.month - 1 + months - (0 if exclusive_end else 1)
    if last_index > 9999 * 12 + 11:
        raise ValueError("The requested period extends beyond the supported calendar (year 9999).")
