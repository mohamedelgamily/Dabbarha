from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from app.core.forecast import (
    ForecastObligation,
    add_months,
    build_forecast,
    month_index,
    month_start,
)


@dataclass(frozen=True)
class ProposedCommitment:
    amount: Decimal
    start_date: date
    term_months: int

    def __post_init__(self) -> None:
        if self.amount < Decimal("0.00"):
            raise ValueError("commitment amount must be greater than or equal to 0.00")
        if self.term_months <= 0:
            raise ValueError("commitment term_months must be greater than 0")


@dataclass(frozen=True)
class MonthlyAffordabilityResult:
    month: date
    income: Decimal
    fixed_expenses: Decimal
    existing_obligation_payments: Decimal
    proposed_commitment_amount: Decimal
    projected_buffer: Decimal


@dataclass(frozen=True)
class AffordabilityResult:
    classification: str
    worst_projected_buffer: Decimal
    worst_buffer_percentage: Decimal
    worst_month: date
    monthly_results: tuple[MonthlyAffordabilityResult, ...]
    explanation: str


def evaluate_affordability(
    *,
    monthly_income: Decimal,
    fixed_expenses: Decimal,
    existing_obligations: Iterable[ForecastObligation],
    proposed_commitment: ProposedCommitment,
    start_month: date,
    months: int,
) -> AffordabilityResult:
    if months < 0:
        raise ValueError("months must be greater than or equal to 0")

    forecast_start = month_start(start_month)
    commitment_start = month_start(proposed_commitment.start_date)
    commitment_end = add_months(commitment_start, proposed_commitment.term_months)
    forecast_end = add_months(forecast_start, months)

    if commitment_start < forecast_start:
        raise ValueError(
            f"Forecast start {forecast_start} is after commitment start {commitment_start}; "
            "the forecast must cover the entire commitment period."
        )
    if commitment_end > forecast_end:
        raise ValueError(
            f"Forecast end {forecast_end} is before commitment end {commitment_end}; "
            "the forecast must cover the entire commitment period."
        )

    base_forecast = build_forecast(
        monthly_income=monthly_income,
        fixed_expenses=fixed_expenses,
        obligations=existing_obligations,
        start_month=start_month,
        months=months,
    )

    monthly_results: list[MonthlyAffordabilityResult] = []
    for month_forecast in base_forecast:
        proposed_amount = _commitment_amount_in_month(proposed_commitment, month_forecast.month)
        projected_buffer = (
            month_forecast.income
            - month_forecast.fixed_expenses
            - month_forecast.obligation_payments
            - proposed_amount
        )

        monthly_results.append(
            MonthlyAffordabilityResult(
                month=month_forecast.month,
                income=month_forecast.income,
                fixed_expenses=month_forecast.fixed_expenses,
                existing_obligation_payments=month_forecast.obligation_payments,
                proposed_commitment_amount=proposed_amount,
                projected_buffer=projected_buffer,
            )
        )

    if not monthly_results:
        return AffordabilityResult(
            classification="Comfortable",
            worst_projected_buffer=Decimal("0.00"),
            worst_buffer_percentage=Decimal("0.00"),
            worst_month=forecast_start,
            monthly_results=(),
            explanation="No months to evaluate.",
        )

    worst_result = min(monthly_results, key=lambda r: r.projected_buffer)

    if worst_result.projected_buffer < Decimal("0.00"):
        classification = "Not Affordable"
        explanation = "This commitment is not affordable with your current income and expenses."
        if monthly_income > Decimal("0.00"):
            worst_buffer_pct = (worst_result.projected_buffer / monthly_income) * Decimal("100")
        else:
            worst_buffer_pct = Decimal("0.00")
    elif monthly_income > Decimal("0.00"):
        worst_buffer_pct = (worst_result.projected_buffer / monthly_income) * Decimal("100")
        if worst_buffer_pct < Decimal("20.00"):
            classification = "Risky"
            explanation = "Possible, but your remaining buffer would be low."
        elif worst_buffer_pct < Decimal("40.00"):
            classification = "Manageable"
            explanation = "This commitment looks manageable."
        else:
            classification = "Comfortable"
            explanation = "This commitment appears affordable."
    else:
        worst_buffer_pct = Decimal("0.00")
        classification = "Risky"
        explanation = "Possible, but your remaining buffer would be low."

    return AffordabilityResult(
        classification=classification,
        worst_projected_buffer=worst_result.projected_buffer,
        worst_buffer_percentage=worst_buffer_pct,
        worst_month=worst_result.month,
        monthly_results=tuple(monthly_results),
        explanation=explanation,
    )


def _commitment_amount_in_month(commitment: ProposedCommitment, month: date) -> Decimal:
    months_since_start = month_index(month_start(month)) - month_index(month_start(commitment.start_date))
    if 0 <= months_since_start < commitment.term_months:
        return commitment.amount
    return Decimal("0.00")
