"""Deterministic installment schedule generation for explicitly opted-in plans."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Literal

from app.schemas.validation import MAX_MONEY, MAX_TERM_MONTHS

CENT = Decimal("0.01")
RATE_QUANTUM = Decimal("0.0001")
MAX_RATE = Decimal("100.0000")
PaymentMethod = Literal["manual", "automatic"]
InterestMethod = Literal["none", "flat", "reducing_balance"]


@dataclass(frozen=True)
class InstallmentSpec:
    number: int
    due_date: date
    amount: Decimal
    principal: Decimal | None
    interest: Decimal | None


def to_cents(amount: Decimal) -> int:
    return int((amount * 100).to_integral_exact())


def from_cents(cents: int) -> Decimal:
    return (Decimal(cents) / 100).quantize(CENT)


def month_date(start: date, offset: int, due_day: int) -> date:
    index = start.year * 12 + start.month - 1 + offset
    year, month0 = divmod(index, 12)
    month = month0 + 1
    return date(year, month, min(due_day, calendar.monthrange(year, month)[1]))


def split_cents(total: int, count: int) -> list[int]:
    quotient, remainder = divmod(total, count)
    return [quotient + (1 if i < remainder else 0) for i in range(count)]


def split_with_final_adjustment(total: int, count: int) -> list[int]:
    quotient, _remainder = divmod(total, count)
    parts = [quotient] * count
    parts[-1] = total - quotient * (count - 1)
    return parts


def _validate_rate(rate: Decimal | None) -> Decimal:
    if rate is None:
        return Decimal("0.0000")
    if not rate.is_finite() or rate.is_signed() or rate < 0 or rate > MAX_RATE:
        raise ValueError("Nominal annual interest rate must be between 0% and 100%.")
    if rate.as_tuple().exponent < -4:
        raise ValueError("Nominal annual interest rate supports up to four decimal places.")
    return rate.quantize(RATE_QUANTUM)


def build_installment_schedule(
    *,
    purchase_price: Decimal,
    down_payment_amount: Decimal,
    start_date: date,
    term_months: int,
    due_day: int,
    payment_method: PaymentMethod,
    interest_method: InterestMethod,
    nominal_annual_interest_rate: Decimal | None,
    manual_monthly_amount: Decimal | None = None,
) -> tuple[InstallmentSpec, ...]:
    """Build a durable schedule; all returned money values have cent precision."""
    if not 1 <= term_months <= MAX_TERM_MONTHS:
        raise ValueError("Installment duration must be between 1 and 1,200 months.")
    if purchase_price <= 0 or purchase_price > MAX_MONEY:
        raise ValueError("Purchase price must be greater than zero and within the supported amount range.")
    if down_payment_amount < 0 or down_payment_amount >= purchase_price:
        raise ValueError("Down payment must be less than the purchase price.")
    rate = _validate_rate(nominal_annual_interest_rate)
    if payment_method == "manual":
        if manual_monthly_amount is None or not 0 < manual_monthly_amount <= MAX_MONEY:
            raise ValueError("Enter a valid provider monthly installment amount.")
        # A disclosed rate is metadata only for manual payments.
        rows = tuple(
            InstallmentSpec(i + 1, month_date(start_date, i, due_day), manual_monthly_amount, None, None)
            for i in range(term_months)
        )
        _validate_schedule(rows, down_payment_amount)
        return rows
    if manual_monthly_amount is not None:
        raise ValueError("Do not send a manual monthly amount for an automatic calculation.")
    if interest_method == "none" and rate != 0:
        raise ValueError("No-interest plans must use a 0% annual rate.")

    principal_cents = to_cents(purchase_price - down_payment_amount)
    with localcontext() as context:
        context.prec = 50
        if interest_method == "none" or rate == 0:
            principals = split_cents(principal_cents, term_months)
            return tuple(
                InstallmentSpec(
                    i + 1,
                    month_date(start_date, i, due_day),
                    from_cents(principals[i]),
                    from_cents(principals[i]),
                    Decimal("0.00"),
                )
                for i in range(term_months)
            )

        if interest_method == "flat":
            interest_total_cents = int(
                (Decimal(principal_cents) * rate * term_months / Decimal("1200")).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            principal_parts = split_with_final_adjustment(principal_cents, term_months)
            interest_parts = split_with_final_adjustment(interest_total_cents, term_months)
            rows = tuple(
                InstallmentSpec(
                    i + 1,
                    month_date(start_date, i, due_day),
                    from_cents(principal_parts[i] + interest_parts[i]),
                    from_cents(principal_parts[i]),
                    from_cents(interest_parts[i]),
                )
                for i in range(term_months)
            )
            _validate_schedule(rows, down_payment_amount)
            return rows

        monthly_rate = rate / Decimal("1200")
        factor = (Decimal(1) + monthly_rate) ** (-term_months)
        exact_payment_cents = Decimal(principal_cents) * monthly_rate / (Decimal(1) - factor)
        regular_payment_cents = int(exact_payment_cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        balance_cents = principal_cents
        rows_list: list[InstallmentSpec] = []
        for index in range(term_months):
            interest_cents = int(
                (Decimal(balance_cents) * monthly_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            if index == term_months - 1:
                principal_part_cents = balance_cents
                amount_cents = principal_part_cents + interest_cents
            else:
                amount_cents = regular_payment_cents
                principal_part_cents = amount_cents - interest_cents
                if principal_part_cents <= 0 or principal_part_cents >= balance_cents:
                    raise ValueError("This rate and term do not produce a supported amortizing schedule.")
            balance_cents -= principal_part_cents
            rows_list.append(
                InstallmentSpec(
                    index + 1,
                    month_date(start_date, index, due_day),
                    from_cents(amount_cents),
                    from_cents(principal_part_cents),
                    from_cents(interest_cents),
                )
            )
        if balance_cents != 0:
            raise ValueError("This rate and term do not fully repay the financed balance.")
        rows = tuple(rows_list)
        _validate_schedule(rows, down_payment_amount)
        return rows


def _validate_schedule(rows: tuple[InstallmentSpec, ...], down_payment_amount: Decimal = Decimal("0.00")) -> None:
    if any(row.amount > MAX_MONEY for row in rows):
        raise ValueError("A scheduled installment exceeds the supported amount range.")
    if any(row.principal is not None and row.interest is not None and row.amount != row.principal + row.interest for row in rows):
        raise ValueError("Installment principal and interest do not reconcile with its scheduled amount.")
    if sum((row.amount for row in rows), Decimal("0.00")) > MAX_MONEY:
        raise ValueError("The total scheduled payments exceed the supported amount range.")
    if sum((row.amount for row in rows), down_payment_amount) > MAX_MONEY:
        raise ValueError("The total plan payments exceed the supported amount range.")
