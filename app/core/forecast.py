from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Protocol


PAYABLE_OBLIGATION_STATUSES = frozenset({"active", "late"})


class ForecastObligation(Protocol):
    monthly_installment_amount: Decimal
    start_date: date
    term_months: int
    status: str


@dataclass(frozen=True)
class MonthlyForecast:
    month: date
    income: Decimal
    fixed_expenses: Decimal
    obligation_payments: Decimal
    projected_buffer: Decimal
    has_negative_buffer: bool


def build_forecast(
    *,
    monthly_income: Decimal,
    fixed_expenses: Decimal,
    obligations: Iterable[ForecastObligation],
    start_month: date,
    months: int,
) -> list[MonthlyForecast]:
    if months < 0:
        raise ValueError("months must be greater than or equal to 0")

    forecast_start = month_start(start_month)
    obligation_list = list(obligations)

    return [
        _build_month_forecast(
            month=add_months(forecast_start, month_offset),
            monthly_income=monthly_income,
            fixed_expenses=fixed_expenses,
            obligations=obligation_list,
        )
        for month_offset in range(months)
    ]


def _build_month_forecast(
    *,
    month: date,
    monthly_income: Decimal,
    fixed_expenses: Decimal,
    obligations: Iterable[ForecastObligation],
) -> MonthlyForecast:
    obligation_payments = sum(
        (
            obligation.monthly_installment_amount
            for obligation in obligations
            if obligation_is_payable_in_month(obligation, month)
        ),
        Decimal("0.00"),
    )
    projected_buffer = monthly_income - fixed_expenses - obligation_payments

    return MonthlyForecast(
        month=month,
        income=monthly_income,
        fixed_expenses=fixed_expenses,
        obligation_payments=obligation_payments,
        projected_buffer=projected_buffer,
        has_negative_buffer=projected_buffer < Decimal("0.00"),
    )


def obligation_is_payable_in_month(obligation: ForecastObligation, month: date) -> bool:
    if obligation.status not in PAYABLE_OBLIGATION_STATUSES:
        return False

    months_since_start = month_index(month_start(month)) - month_index(month_start(obligation.start_date))
    return 0 <= months_since_start < obligation.term_months


def add_months(value: date, months: int) -> date:
    month_number = value.year * 12 + value.month - 1 + months
    year, month_index_in_year = divmod(month_number, 12)
    return date(year, month_index_in_year + 1, 1)


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def month_index(value: date) -> int:
    return value.year * 12 + value.month
