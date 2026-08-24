from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.obligation import ObligationCreate, ObligationResponse


def test_valid_obligation_create_accepted() -> None:
    data = {
        "provider": "valU",
        "item_name": "MacBook Pro",
        "category": "Electronics",
        "total_amount": "24000.00",
        "monthly_installment_amount": "2000.00",
        "start_date": "2026-01-01",
        "term_months": 12,
        "due_day_of_month": 5,
    }
    obligation = ObligationCreate(**data)
    assert obligation.provider == "valU"
    assert obligation.item_name == "MacBook Pro"
    assert obligation.category == "Electronics"
    assert obligation.total_amount == Decimal("24000.00")
    assert obligation.monthly_installment_amount == Decimal("2000.00")
    assert obligation.start_date == date(2026, 1, 1)
    assert obligation.term_months == 12
    assert obligation.due_day_of_month == 5
    assert obligation.status == "active"
    assert obligation.source == "manual_entry"


@pytest.mark.parametrize("status", ["active", "completed", "late", "defaulted"])
def test_all_allowed_status_values_accepted(status: str) -> None:
    data = {
        "provider": "aman",
        "item_name": "Phone",
        "category": "Electronics",
        "total_amount": "10000.00",
        "monthly_installment_amount": "1000.00",
        "start_date": "2026-03-01",
        "term_months": 10,
        "due_day_of_month": 15,
        "status": status,
    }
    obligation = ObligationCreate(**data)
    assert obligation.status == status


@pytest.mark.parametrize("source", ["manual_entry", "chatbot_entry"])
def test_all_allowed_source_values_accepted(source: str) -> None:
    data = {
        "provider": "souhoola",
        "item_name": "Washing Machine",
        "category": "Appliances",
        "total_amount": "15000.00",
        "monthly_installment_amount": "1500.00",
        "start_date": "2026-02-01",
        "term_months": 10,
        "due_day_of_month": 20,
        "source": source,
    }
    obligation = ObligationCreate(**data)
    assert obligation.source == source


def test_negative_total_amount_rejected() -> None:
    data = {
        "provider": "valU",
        "item_name": "TV",
        "category": "Electronics",
        "total_amount": "-100.00",
        "monthly_installment_amount": "50.00",
        "start_date": "2026-01-01",
        "term_months": 12,
        "due_day_of_month": 5,
    }
    with pytest.raises(ValidationError):
        ObligationCreate(**data)


def test_negative_monthly_installment_amount_rejected() -> None:
    data = {
        "provider": "valU",
        "item_name": "TV",
        "category": "Electronics",
        "total_amount": "1000.00",
        "monthly_installment_amount": "-50.00",
        "start_date": "2026-01-01",
        "term_months": 12,
        "due_day_of_month": 5,
    }
    with pytest.raises(ValidationError):
        ObligationCreate(**data)


@pytest.mark.parametrize("invalid_term_months", [0, -1, -12])
def test_term_months_less_than_or_equal_to_zero_rejected(invalid_term_months: int) -> None:
    data = {
        "provider": "valU",
        "item_name": "TV",
        "category": "Electronics",
        "total_amount": "1000.00",
        "monthly_installment_amount": "50.00",
        "start_date": "2026-01-01",
        "term_months": invalid_term_months,
        "due_day_of_month": 5,
    }
    with pytest.raises(ValidationError):
        ObligationCreate(**data)


@pytest.mark.parametrize("invalid_due_day", [0, -1, -10])
def test_due_day_of_month_below_one_rejected(invalid_due_day: int) -> None:
    data = {
        "provider": "valU",
        "item_name": "TV",
        "category": "Electronics",
        "total_amount": "1000.00",
        "monthly_installment_amount": "50.00",
        "start_date": "2026-01-01",
        "term_months": 12,
        "due_day_of_month": invalid_due_day,
    }
    with pytest.raises(ValidationError):
        ObligationCreate(**data)


@pytest.mark.parametrize("invalid_due_day", [32, 50, 100])
def test_due_day_of_month_above_31_rejected(invalid_due_day: int) -> None:
    data = {
        "provider": "valU",
        "item_name": "TV",
        "category": "Electronics",
        "total_amount": "1000.00",
        "monthly_installment_amount": "50.00",
        "start_date": "2026-01-01",
        "term_months": 12,
        "due_day_of_month": invalid_due_day,
    }
    with pytest.raises(ValidationError):
        ObligationCreate(**data)


@pytest.mark.parametrize("invalid_status", ["paused", "canceled", "unknown", ""])
def test_invalid_status_rejected(invalid_status: str) -> None:
    data = {
        "provider": "valU",
        "item_name": "TV",
        "category": "Electronics",
        "total_amount": "1000.00",
        "monthly_installment_amount": "50.00",
        "start_date": "2026-01-01",
        "term_months": 12,
        "due_day_of_month": 5,
        "status": invalid_status,
    }
    with pytest.raises(ValidationError):
        ObligationCreate(**data)


@pytest.mark.parametrize("invalid_source", ["spreadsheet_import", "bank_sync", "api", ""])
def test_invalid_source_rejected(invalid_source: str) -> None:
    data = {
        "provider": "valU",
        "item_name": "TV",
        "category": "Electronics",
        "total_amount": "1000.00",
        "monthly_installment_amount": "50.00",
        "start_date": "2026-01-01",
        "term_months": 12,
        "due_day_of_month": 5,
        "source": invalid_source,
    }
    with pytest.raises(ValidationError):
        ObligationCreate(**data)


def test_user_id_not_accepted_in_obligation_create() -> None:
    assert "user_id" not in ObligationCreate.model_fields

    data = {
        "user_id": 42,
        "provider": "valU",
        "item_name": "TV",
        "category": "Electronics",
        "total_amount": "1000.00",
        "monthly_installment_amount": "50.00",
        "start_date": "2026-01-01",
        "term_months": 12,
        "due_day_of_month": 5,
    }
    with pytest.raises(ValidationError):
        ObligationCreate(**data)


def test_obligation_response_schema_valid() -> None:
    now = datetime.now(timezone.utc)
    response_data = {
        "id": 1,
        "user_id": 10,
        "provider": "valU",
        "item_name": "Refrigerator",
        "category": "Appliances",
        "total_amount": Decimal("18000.00"),
        "monthly_installment_amount": Decimal("1500.00"),
        "start_date": date(2026, 1, 15),
        "term_months": 12,
        "due_day_of_month": 15,
        "status": "active",
        "source": "manual_entry",
        "created_at": now,
        "updated_at": now,
    }
    response = ObligationResponse(**response_data)
    assert response.id == 1
    assert response.user_id == 10
    assert response.provider == "valU"
    assert response.total_amount == Decimal("18000.00")
    assert response.created_at == now
