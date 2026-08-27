from datetime import date
from decimal import Decimal

import pytest

from app.core.forecast import build_forecast, obligation_is_payable_in_month
from app.models.obligation import Obligation


def make_obligation(**overrides) -> Obligation:
    values = {
        "user_id": 1,
        "provider": "valU",
        "item_name": "Laptop",
        "category": "Electronics",
        "total_amount": Decimal("12000.00"),
        "monthly_installment_amount": Decimal("1000.00"),
        "start_date": date(2026, 1, 15),
        "term_months": 3,
        "due_day_of_month": 15,
        "status": "active",
    }
    values.update(overrides)
    return Obligation(**values)


def test_forecast_returns_one_row_per_month_from_normalized_start_month() -> None:
    forecast = build_forecast(
        monthly_income=Decimal("10000.00"),
        fixed_expenses=Decimal("2500.00"),
        obligations=[],
        start_month=date(2026, 1, 27),
        months=3,
    )

    assert [month.month for month in forecast] == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]
    assert all(month.income == Decimal("10000.00") for month in forecast)
    assert all(month.fixed_expenses == Decimal("2500.00") for month in forecast)


def test_forecast_counts_obligation_from_start_month_through_term_only() -> None:
    obligation = make_obligation(start_date=date(2026, 2, 20), term_months=2)

    forecast = build_forecast(
        monthly_income=Decimal("10000.00"),
        fixed_expenses=Decimal("2000.00"),
        obligations=[obligation],
        start_month=date(2026, 1, 1),
        months=4,
    )

    assert [month.obligation_payments for month in forecast] == [
        Decimal("0.00"),
        Decimal("1000.00"),
        Decimal("1000.00"),
        Decimal("0.00"),
    ]


def test_forecast_counts_obligation_that_started_before_forecast_period() -> None:
    obligation = make_obligation(start_date=date(2025, 11, 1), term_months=4)

    forecast = build_forecast(
        monthly_income=Decimal("10000.00"),
        fixed_expenses=Decimal("2500.00"),
        obligations=[obligation],
        start_month=date(2026, 1, 1),
        months=3,
    )

    assert [month.obligation_payments for month in forecast] == [
        Decimal("1000.00"),
        Decimal("1000.00"),
        Decimal("0.00"),
    ]


def test_forecast_ignores_obligation_starting_after_forecast_period() -> None:
    obligation = make_obligation(start_date=date(2026, 5, 1), term_months=12)

    forecast = build_forecast(
        monthly_income=Decimal("10000.00"),
        fixed_expenses=Decimal("2500.00"),
        obligations=[obligation],
        start_month=date(2026, 1, 1),
        months=3,
    )

    assert [month.obligation_payments for month in forecast] == [
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    ]
    assert [month.projected_buffer for month in forecast] == [
        Decimal("7500.00"),
        Decimal("7500.00"),
        Decimal("7500.00"),
    ]


def test_forecast_sums_multiple_payable_obligations() -> None:
    obligations = [
        make_obligation(monthly_installment_amount=Decimal("1000.00")),
        make_obligation(monthly_installment_amount=Decimal("750.50"), status="late"),
    ]

    forecast = build_forecast(
        monthly_income=Decimal("7000.00"),
        fixed_expenses=Decimal("2500.00"),
        obligations=obligations,
        start_month=date(2026, 1, 1),
        months=1,
    )

    assert forecast[0].obligation_payments == Decimal("1750.50")
    assert forecast[0].projected_buffer == Decimal("2749.50")
    assert forecast[0].has_negative_buffer is False


@pytest.mark.parametrize("status", ["completed", "defaulted"])
def test_forecast_excludes_non_payable_obligation_statuses(status: str) -> None:
    obligation = make_obligation(status=status)

    forecast = build_forecast(
        monthly_income=Decimal("5000.00"),
        fixed_expenses=Decimal("1000.00"),
        obligations=[obligation],
        start_month=date(2026, 1, 1),
        months=1,
    )

    assert forecast[0].obligation_payments == Decimal("0.00")
    assert forecast[0].projected_buffer == Decimal("4000.00")


def test_forecast_flags_negative_buffer() -> None:
    obligation = make_obligation(monthly_installment_amount=Decimal("3000.00"))

    forecast = build_forecast(
        monthly_income=Decimal("5000.00"),
        fixed_expenses=Decimal("2500.00"),
        obligations=[obligation],
        start_month=date(2026, 1, 1),
        months=1,
    )

    assert forecast[0].projected_buffer == Decimal("-500.00")
    assert forecast[0].has_negative_buffer is True


def test_forecast_does_not_flag_zero_projected_buffer_as_negative() -> None:
    obligation = make_obligation(monthly_installment_amount=Decimal("1500.00"))

    forecast = build_forecast(
        monthly_income=Decimal("5000.00"),
        fixed_expenses=Decimal("3500.00"),
        obligations=[obligation],
        start_month=date(2026, 1, 1),
        months=1,
    )

    assert forecast[0].projected_buffer == Decimal("0.00")
    assert forecast[0].has_negative_buffer is False


def test_forecast_buffer_changes_as_obligation_starts_and_ends() -> None:
    obligation = make_obligation(
        monthly_installment_amount=Decimal("1500.00"),
        start_date=date(2026, 2, 10),
        term_months=3,
    )

    forecast = build_forecast(
        monthly_income=Decimal("8000.00"),
        fixed_expenses=Decimal("3000.00"),
        obligations=[obligation],
        start_month=date(2026, 1, 1),
        months=5,
    )

    assert [month.obligation_payments for month in forecast] == [
        Decimal("0.00"),
        Decimal("1500.00"),
        Decimal("1500.00"),
        Decimal("1500.00"),
        Decimal("0.00"),
    ]
    assert [month.projected_buffer for month in forecast] == [
        Decimal("5000.00"),
        Decimal("3500.00"),
        Decimal("3500.00"),
        Decimal("3500.00"),
        Decimal("5000.00"),
    ]


def test_forecast_treats_mid_month_start_as_payable_for_that_calendar_month() -> None:
    obligation = make_obligation(start_date=date(2026, 3, 31), term_months=1)

    forecast = build_forecast(
        monthly_income=Decimal("6000.00"),
        fixed_expenses=Decimal("2000.00"),
        obligations=[obligation],
        start_month=date(2026, 3, 1),
        months=2,
    )

    assert [month.obligation_payments for month in forecast] == [
        Decimal("1000.00"),
        Decimal("0.00"),
    ]


def test_forecast_handles_zero_months() -> None:
    assert (
        build_forecast(
            monthly_income=Decimal("5000.00"),
            fixed_expenses=Decimal("2500.00"),
            obligations=[make_obligation()],
            start_month=date(2026, 1, 1),
            months=0,
        )
        == []
    )


def test_forecast_rejects_negative_month_count() -> None:
    with pytest.raises(ValueError, match="months"):
        build_forecast(
            monthly_income=Decimal("5000.00"),
            fixed_expenses=Decimal("2500.00"),
            obligations=[],
            start_month=date(2026, 1, 1),
            months=-1,
        )


def test_obligation_payability_uses_calendar_months_across_year_boundaries() -> None:
    obligation = make_obligation(start_date=date(2026, 12, 31), term_months=2)

    assert obligation_is_payable_in_month(obligation, date(2026, 11, 1)) is False
    assert obligation_is_payable_in_month(obligation, date(2026, 12, 1)) is True
    assert obligation_is_payable_in_month(obligation, date(2027, 1, 1)) is True
    assert obligation_is_payable_in_month(obligation, date(2027, 2, 1)) is False
