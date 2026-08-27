from datetime import date
from decimal import Decimal
from typing import Optional

import pytest

from app.core.affordability import (
    AffordabilityResult,
    MonthlyAffordabilityResult,
    ProposedCommitment,
    evaluate_affordability,
)
from app.core.forecast import ForecastObligation


class MockObligation:
    def __init__(
        self,
        *,
        monthly_installment_amount: Decimal = Decimal("0.00"),
        start_date: date = date(2026, 1, 1),
        term_months: int = 1,
        status: str = "active",
    ) -> None:
        self.monthly_installment_amount = monthly_installment_amount
        self.start_date = start_date
        self.term_months = term_months
        self.status = status


def make_commitment(
    *,
    amount: Decimal = Decimal("0.00"),
    start_date: date = date(2026, 1, 1),
    term_months: int = 1,
) -> ProposedCommitment:
    return ProposedCommitment(
        amount=amount,
        start_date=start_date,
        term_months=term_months,
    )


def test_comfortable_classification() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("10000.00"),
        fixed_expenses=Decimal("2000.00"),
        existing_obligations=[],
        proposed_commitment=make_commitment(amount=Decimal("1000.00")),
        start_month=date(2026, 1, 1),
        months=1,
    )

    assert result.classification == "Comfortable"
    assert result.worst_projected_buffer == Decimal("7000.00")
    assert result.worst_buffer_percentage == Decimal("70.00")
    assert result.worst_month == date(2026, 1, 1)
    assert result.explanation == "This commitment appears affordable."
    assert len(result.monthly_results) == 1
    assert result.monthly_results[0].proposed_commitment_amount == Decimal("1000.00")


def test_manageable_classification() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("5000.00"),
        fixed_expenses=Decimal("2500.00"),
        existing_obligations=[],
        proposed_commitment=make_commitment(amount=Decimal("1000.00")),
        start_month=date(2026, 1, 1),
        months=1,
    )

    assert result.classification == "Manageable"
    assert result.worst_projected_buffer == Decimal("1500.00")
    assert result.worst_buffer_percentage == Decimal("30.00")
    assert result.worst_month == date(2026, 1, 1)
    assert result.explanation == "This commitment looks manageable."


def test_risky_classification() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("5000.00"),
        fixed_expenses=Decimal("4000.00"),
        existing_obligations=[],
        proposed_commitment=make_commitment(amount=Decimal("500.00")),
        start_month=date(2026, 1, 1),
        months=1,
    )

    assert result.classification == "Risky"
    assert result.worst_projected_buffer == Decimal("500.00")
    assert result.worst_buffer_percentage == Decimal("10.00")
    assert result.worst_month == date(2026, 1, 1)
    assert result.explanation == "Possible, but your remaining buffer would be low."


def test_risky_exactly_zero_percent() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("5000.00"),
        fixed_expenses=Decimal("4000.00"),
        existing_obligations=[],
        proposed_commitment=make_commitment(amount=Decimal("1000.00")),
        start_month=date(2026, 1, 1),
        months=1,
    )

    assert result.classification == "Risky"
    assert result.worst_projected_buffer == Decimal("0.00")
    assert result.worst_buffer_percentage == Decimal("0.00")
    assert result.worst_month == date(2026, 1, 1)
    assert result.explanation == "Possible, but your remaining buffer would be low."


def test_not_affordable_negative_buffer() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("5000.00"),
        fixed_expenses=Decimal("4000.00"),
        existing_obligations=[],
        proposed_commitment=make_commitment(amount=Decimal("2000.00")),
        start_month=date(2026, 1, 1),
        months=1,
    )

    assert result.classification == "Not Affordable"
    assert result.worst_projected_buffer == Decimal("-1000.00")
    assert result.worst_buffer_percentage == Decimal("-20.00")
    assert result.worst_month == date(2026, 1, 1)
    assert result.explanation == "This commitment is not affordable with your current income and expenses."


def test_worst_month_determines_classification() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("5000.00"),
        fixed_expenses=Decimal("2000.00"),
        existing_obligations=[],
        proposed_commitment=make_commitment(
            amount=Decimal("2500.00"),
            start_date=date(2026, 2, 1),
            term_months=1,
        ),
        start_month=date(2026, 1, 1),
        months=3,
    )

    assert result.classification == "Risky"
    assert result.worst_month == date(2026, 2, 1)
    assert result.worst_projected_buffer == Decimal("500.00")
    assert result.worst_buffer_percentage == Decimal("10.00")
    assert result.monthly_results[0].projected_buffer == Decimal("3000.00")
    assert result.monthly_results[1].projected_buffer == Decimal("500.00")
    assert result.monthly_results[2].projected_buffer == Decimal("3000.00")


def test_commitment_spanning_multiple_months() -> None:
    existing = MockObligation(
        monthly_installment_amount=Decimal("1000.00"),
        start_date=date(2026, 1, 1),
        term_months=1,
    )
    result = evaluate_affordability(
        monthly_income=Decimal("10000.00"),
        fixed_expenses=Decimal("3000.00"),
        existing_obligations=[existing],
        proposed_commitment=make_commitment(
            amount=Decimal("2000.00"),
            start_date=date(2026, 1, 1),
            term_months=3,
        ),
        start_month=date(2026, 1, 1),
        months=4,
    )

    assert result.classification == "Comfortable"
    assert result.worst_month == date(2026, 1, 1)
    assert result.worst_projected_buffer == Decimal("4000.00")
    assert result.worst_buffer_percentage == Decimal("40.00")
    assert len(result.monthly_results) == 4
    assert result.monthly_results[0].proposed_commitment_amount == Decimal("2000.00")
    assert result.monthly_results[0].existing_obligation_payments == Decimal("1000.00")
    assert result.monthly_results[1].proposed_commitment_amount == Decimal("2000.00")
    assert result.monthly_results[1].existing_obligation_payments == Decimal("0.00")
    assert result.monthly_results[2].proposed_commitment_amount == Decimal("2000.00")
    assert result.monthly_results[3].proposed_commitment_amount == Decimal("0.00")


def test_one_time_cash_commitment() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("10000.00"),
        fixed_expenses=Decimal("2000.00"),
        existing_obligations=[],
        proposed_commitment=make_commitment(
            amount=Decimal("3000.00"),
            start_date=date(2026, 1, 1),
            term_months=1,
        ),
        start_month=date(2026, 1, 1),
        months=2,
    )

    assert result.classification == "Comfortable"
    assert result.worst_month == date(2026, 1, 1)
    assert result.worst_projected_buffer == Decimal("5000.00")
    assert result.worst_buffer_percentage == Decimal("50.00")
    assert result.monthly_results[0].proposed_commitment_amount == Decimal("3000.00")
    assert result.monthly_results[1].proposed_commitment_amount == Decimal("0.00")


def test_recurring_commitment() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("8000.00"),
        fixed_expenses=Decimal("3000.00"),
        existing_obligations=[],
        proposed_commitment=make_commitment(
            amount=Decimal("1500.00"),
            start_date=date(2026, 1, 1),
            term_months=6,
        ),
        start_month=date(2026, 1, 1),
        months=6,
    )

    assert result.classification == "Comfortable"
    assert result.worst_projected_buffer == Decimal("3500.00")
    assert result.worst_buffer_percentage == Decimal("43.75")
    for month_result in result.monthly_results:
        assert month_result.proposed_commitment_amount == Decimal("1500.00")


def test_existing_obligations_combined_with_new_commitment() -> None:
    existing = MockObligation(
        monthly_installment_amount=Decimal("2000.00"),
        start_date=date(2026, 1, 1),
        term_months=3,
    )
    result = evaluate_affordability(
        monthly_income=Decimal("10000.00"),
        fixed_expenses=Decimal("2000.00"),
        existing_obligations=[existing],
        proposed_commitment=make_commitment(
            amount=Decimal("1500.00"),
            start_date=date(2026, 1, 1),
            term_months=3,
        ),
        start_month=date(2026, 1, 1),
        months=3,
    )

    assert result.classification == "Comfortable"
    assert result.worst_projected_buffer == Decimal("4500.00")
    assert result.worst_buffer_percentage == Decimal("45.00")
    for month_result in result.monthly_results:
        assert month_result.existing_obligation_payments == Decimal("2000.00")
        assert month_result.proposed_commitment_amount == Decimal("1500.00")


def test_zero_income_risky_with_zero_buffer() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("0.00"),
        fixed_expenses=Decimal("0.00"),
        existing_obligations=[],
        proposed_commitment=make_commitment(amount=Decimal("0.00")),
        start_month=date(2026, 1, 1),
        months=1,
    )

    assert result.classification == "Risky"
    assert result.worst_projected_buffer == Decimal("0.00")
    assert result.worst_buffer_percentage == Decimal("0.00")
    assert result.explanation == "Possible, but your remaining buffer would be low."


def test_zero_income_not_affordable_with_negative_buffer() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("0.00"),
        fixed_expenses=Decimal("1000.00"),
        existing_obligations=[],
        proposed_commitment=make_commitment(amount=Decimal("0.00")),
        start_month=date(2026, 1, 1),
        months=1,
    )

    assert result.classification == "Not Affordable"
    assert result.worst_projected_buffer == Decimal("-1000.00")
    assert result.worst_buffer_percentage == Decimal("0.00")
    assert result.explanation == "This commitment is not affordable with your current income and expenses."


def test_decimal_precision_maintained() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("3333.33"),
        fixed_expenses=Decimal("1111.11"),
        existing_obligations=[],
        proposed_commitment=make_commitment(amount=Decimal("555.55")),
        start_month=date(2026, 1, 1),
        months=1,
    )

    assert result.worst_projected_buffer == Decimal("1666.67")
    assert result.worst_buffer_percentage == Decimal("1666.67") / Decimal("3333.33") * Decimal("100")
    assert result.classification == "Comfortable"


def test_commitment_period_boundaries_mid_month_start() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("6000.00"),
        fixed_expenses=Decimal("2000.00"),
        existing_obligations=[],
        proposed_commitment=make_commitment(
            amount=Decimal("1000.00"),
            start_date=date(2026, 1, 15),
            term_months=1,
        ),
        start_month=date(2026, 1, 1),
        months=2,
    )

    assert result.monthly_results[0].proposed_commitment_amount == Decimal("1000.00")
    assert result.monthly_results[1].proposed_commitment_amount == Decimal("0.00")


def test_commitment_period_boundaries_year_crossing() -> None:
    result = evaluate_affordability(
        monthly_income=Decimal("6000.00"),
        fixed_expenses=Decimal("2000.00"),
        existing_obligations=[],
        proposed_commitment=make_commitment(
            amount=Decimal("1000.00"),
            start_date=date(2026, 12, 15),
            term_months=2,
        ),
        start_month=date(2026, 12, 1),
        months=3,
    )

    assert result.monthly_results[0].proposed_commitment_amount == Decimal("1000.00")
    assert result.monthly_results[1].proposed_commitment_amount == Decimal("1000.00")
    assert result.monthly_results[2].proposed_commitment_amount == Decimal("0.00")


def test_negative_month_count_raises() -> None:
    with pytest.raises(ValueError, match="months"):
        evaluate_affordability(
            monthly_income=Decimal("5000.00"),
            fixed_expenses=Decimal("2000.00"),
            existing_obligations=[],
            proposed_commitment=make_commitment(),
            start_month=date(2026, 1, 1),
            months=-1,
        )


def test_zero_months_raises_when_commitment_not_covered() -> None:
    with pytest.raises(ValueError, match="forecast must cover the entire commitment period"):
        evaluate_affordability(
            monthly_income=Decimal("5000.00"),
            fixed_expenses=Decimal("2000.00"),
            existing_obligations=[],
            proposed_commitment=make_commitment(term_months=1),
            start_month=date(2026, 1, 1),
            months=0,
        )


def test_commitment_extending_beyond_forecast_raises() -> None:
    with pytest.raises(ValueError, match="forecast must cover the entire commitment period"):
        evaluate_affordability(
            monthly_income=Decimal("5000.00"),
            fixed_expenses=Decimal("2000.00"),
            existing_obligations=[],
            proposed_commitment=make_commitment(
                amount=Decimal("1000.00"),
                start_date=date(2026, 1, 1),
                term_months=3,
            ),
            start_month=date(2026, 1, 1),
            months=2,
        )


def test_commitment_starting_before_forecast_raises() -> None:
    with pytest.raises(ValueError, match="forecast must cover the entire commitment period"):
        evaluate_affordability(
            monthly_income=Decimal("5000.00"),
            fixed_expenses=Decimal("2000.00"),
            existing_obligations=[],
            proposed_commitment=make_commitment(
                amount=Decimal("1000.00"),
                start_date=date(2025, 12, 1),
                term_months=1,
            ),
            start_month=date(2026, 1, 1),
            months=1,
        )


def test_proposed_commitment_rejects_negative_amount() -> None:
    with pytest.raises(ValueError, match="commitment amount must be greater than or equal to 0.00"):
        make_commitment(amount=Decimal("-1.00"))


def test_proposed_commitment_rejects_zero_term_months() -> None:
    with pytest.raises(ValueError, match="commitment term_months must be greater than 0"):
        make_commitment(term_months=0)


def test_proposed_commitment_rejects_negative_term_months() -> None:
    with pytest.raises(ValueError, match="commitment term_months must be greater than 0"):
        make_commitment(term_months=-1)
