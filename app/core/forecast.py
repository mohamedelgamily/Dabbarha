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
    purchase_price: Decimal | None
    down_payment_amount: Decimal
    down_payment_date: date | None
    down_payment_paid: bool
    installments: Iterable[object]


@dataclass(frozen=True)
class MonthlyForecast:
    month: date
    income: Decimal
    fixed_expenses: Decimal
    obligation_payments: Decimal
    installment_payments: Decimal
    down_payment_payments: Decimal
    overdue_down_payment_payments: Decimal
    down_payment_details: tuple["DownPaymentProjection", ...]
    projected_buffer: Decimal
    has_negative_buffer: bool


@dataclass(frozen=True)
class DownPaymentProjection:
    obligation_id: int
    original_date: date
    amount: Decimal
    overdue: bool


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
    forecast_start_day = start_month
    obligation_list = list(obligations)

    return [
        _build_month_forecast(
            month=add_months(forecast_start, month_offset),
            monthly_income=monthly_income,
            fixed_expenses=fixed_expenses,
            obligations=obligation_list,
            forecast_start=forecast_start,
            forecast_start_day=forecast_start_day,
        )
        for month_offset in range(months)
    ]


def _build_month_forecast(
    *,
    month: date,
    monthly_income: Decimal,
    fixed_expenses: Decimal,
    obligations: Iterable[ForecastObligation],
    forecast_start: date,
    forecast_start_day: date,
) -> MonthlyForecast:
    installment_payments = Decimal("0.00")
    down_payment_payments = Decimal("0.00")
    overdue_down_payment_payments = Decimal("0.00")
    down_payment_details: list[DownPaymentProjection] = []
    for obligation in obligations:
        if obligation.status not in PAYABLE_OBLIGATION_STATUSES:
            continue
        if getattr(obligation, "purchase_price", None) is None:
            if obligation_is_payable_in_month(obligation, month):
                installment_payments += obligation.monthly_installment_amount
        else:
            installment_payments += sum(
                (
                    row.scheduled_amount
                    for row in getattr(obligation, "installments", ())
                    if month_start(row.due_date) == month
                ),
                Decimal("0.00"),
            )
        down_amount = getattr(obligation, "down_payment_amount", Decimal("0.00")) or Decimal("0.00")
        down_date = getattr(obligation, "down_payment_date", None)
        down_paid = getattr(obligation, "down_payment_paid", False)
        if down_amount > 0 and down_date is not None and not down_paid:
            is_overdue = down_date < forecast_start_day
            if month_start(down_date) == month or (is_overdue and month == forecast_start):
                down_payment_payments += down_amount
                if is_overdue and month == forecast_start:
                    overdue_down_payment_payments += down_amount
                down_payment_details.append(
                    DownPaymentProjection(
                        obligation_id=obligation.id,
                        original_date=down_date,
                        amount=down_amount,
                        overdue=is_overdue,
                    )
                )
    obligation_payments = installment_payments + down_payment_payments
    projected_buffer = monthly_income - fixed_expenses - obligation_payments

    return MonthlyForecast(
        month=month,
        income=monthly_income,
        fixed_expenses=fixed_expenses,
        obligation_payments=obligation_payments,
        installment_payments=installment_payments,
        down_payment_payments=down_payment_payments,
        overdue_down_payment_payments=overdue_down_payment_payments,
        down_payment_details=tuple(down_payment_details),
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
