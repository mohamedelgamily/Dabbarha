from collections.abc import Generator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.forecast import build_forecast
from app.core.installments import build_installment_schedule
from app.core.security import create_access_token
from app.db.database import Base
from app.main import app
from app.models.obligation import Obligation, ObligationInstallment
from app.models.user import User
from app.schemas.obligation import InstallmentPlanCreate


@pytest.fixture
def plan_db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def sqlite_fk(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def plan_client(plan_db: Session) -> Generator[tuple[TestClient, Session, str, int], None, None]:
    user = User(name="Plan Test", email="plan@example.test", password_hash="not-used")
    plan_db.add(user)
    plan_db.commit()
    plan_db.refresh(user)
    token = create_access_token(subject=str(user.id))

    def override_db():
        yield plan_db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, plan_db, f"Bearer {token}", user.id
    finally:
        app.dependency_overrides.clear()


def schedule(**overrides):
    args = dict(
        purchase_price=Decimal("30000.00"),
        down_payment_amount=Decimal("6000.00"),
        start_date=date(2026, 1, 15),
        term_months=12,
        due_day=15,
        payment_method="automatic",
        interest_method="none",
        nominal_annual_interest_rate=None,
    )
    args.update(overrides)
    return build_installment_schedule(**args)


def test_no_interest_cent_remainder_sums_exactly():
    rows = schedule(purchase_price=Decimal("100.00"), down_payment_amount=Decimal("0.00"), term_months=3)
    assert [row.amount for row in rows] == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert sum((row.principal for row in rows), Decimal("0")) == Decimal("100.00")
    assert sum((row.interest for row in rows), Decimal("0")) == Decimal("0.00")


def test_flat_interest_schedule_reconciles_exactly():
    rows = schedule(interest_method="flat", nominal_annual_interest_rate=Decimal("12"))
    assert {row.amount for row in rows} == {Decimal("2240.00")}
    assert sum((row.principal for row in rows), Decimal("0")) == Decimal("24000.00")
    assert sum((row.interest for row in rows), Decimal("0")) == Decimal("2880.00")
    assert sum((row.amount for row in rows), Decimal("0")) == Decimal("26880.00")


def test_flat_interest_final_installment_receives_rounding_remainder():
    rows = schedule(
        purchase_price=Decimal("100.00"), down_payment_amount=Decimal("0.00"), term_months=3,
        interest_method="flat", nominal_annual_interest_rate=Decimal("1"),
    )
    assert [row.amount for row in rows] == [Decimal("33.41"), Decimal("33.41"), Decimal("33.43")]
    assert sum((row.principal for row in rows), Decimal("0")) == Decimal("100.00")
    assert sum((row.interest for row in rows), Decimal("0")) == Decimal("0.25")
    assert sum((row.amount for row in rows), Decimal("0")) == Decimal("100.25")


def test_reducing_balance_final_adjustment_clears_principal():
    rows = schedule(
        purchase_price=Decimal("1000.00"), down_payment_amount=Decimal("0.00"), term_months=3,
        interest_method="reducing_balance", nominal_annual_interest_rate=Decimal("10"),
    )
    assert [row.amount for row in rows] == [Decimal("338.90"), Decimal("338.90"), Decimal("338.91")]
    assert [row.interest for row in rows] == [Decimal("8.33"), Decimal("5.58"), Decimal("2.80")]
    assert sum((row.principal for row in rows), Decimal("0")) == Decimal("1000.00")
    assert sum((row.amount for row in rows), Decimal("0")) == Decimal("1016.71")


@pytest.mark.parametrize(
    "rate", [Decimal("-0.0001"), Decimal("-0.0000"), Decimal("100.0001"), Decimal("1.00001"), Decimal("NaN"), Decimal("Infinity")]
)
def test_invalid_rate_rejected(rate):
    with pytest.raises(ValueError):
        schedule(interest_method="flat", nominal_annual_interest_rate=rate)


@pytest.mark.parametrize("term,expected", [(1, 1), (1200, 1200)])
def test_supported_term_boundaries(term, expected):
    rows = schedule(term_months=term)
    assert len(rows) == expected


@pytest.mark.parametrize("term", [0, 1201, 2**63 - 1])
def test_unsupported_and_extreme_terms_rejected(term):
    with pytest.raises(ValueError, match="1 and 1,200"):
        schedule(term_months=term)


def test_manual_provider_amount_is_not_recalculated_from_disclosed_rate():
    rows = schedule(
        purchase_price=Decimal("1000.00"), down_payment_amount=Decimal("100.00"), term_months=3,
        payment_method="manual", interest_method="flat", nominal_annual_interest_rate=Decimal("12.5"),
        manual_monthly_amount=Decimal("317.25"),
    )
    assert [row.amount for row in rows] == [Decimal("317.25")] * 3
    assert all(row.principal is None and row.interest is None for row in rows)


def test_plan_schema_accepts_max_rate_and_rejects_excess_precision():
    base = {
        "provider": "p", "item_name": "i", "category": "c", "purchase_price": "1000.00",
        "payment_method": "automatic", "interest_method": "flat", "start_date": "2026-01-01",
        "term_months": 1, "due_day_of_month": 1,
    }
    accepted = InstallmentPlanCreate.model_validate(base | {"nominal_annual_interest_rate": "100.0000"})
    assert accepted.nominal_annual_interest_rate == Decimal("100.0000")
    with pytest.raises(ValidationError):
        InstallmentPlanCreate.model_validate(base | {"nominal_annual_interest_rate": "1.00001"})


def test_forecast_uses_schedule_and_projects_overdue_down_payment_once():
    rows = schedule(
        purchase_price=Decimal("100.00"), down_payment_amount=Decimal("0.00"), term_months=3
    )
    obligation = Obligation(
        user_id=1, provider="provider", item_name="item", category="other",
        total_amount=Decimal("100.00"), monthly_installment_amount=rows[0].amount,
        purchase_price=Decimal("100.00"), payment_method="automatic", interest_method="none",
        down_payment_amount=Decimal("10.00"), down_payment_date=date(2026, 1, 3),
        down_payment_paid=False, start_date=date(2026, 1, 1), term_months=3,
        due_day_of_month=1, status="active",
    )
    obligation.id = 123
    obligation.installments = [
        ObligationInstallment(
            installment_number=row.number, due_date=row.due_date,
            scheduled_amount=row.amount, principal_amount=row.principal, interest_amount=row.interest,
        )
        for row in rows
    ]
    forecast = build_forecast(
        monthly_income=Decimal("1000.00"), fixed_expenses=Decimal("0.00"),
        obligations=[obligation], start_month=date(2026, 1, 15), months=3,
    )
    assert forecast[0].installment_payments == Decimal("33.34")
    assert forecast[0].down_payment_payments == Decimal("10.00")
    assert forecast[0].overdue_down_payment_payments == Decimal("10.00")
    assert forecast[0].obligation_payments == Decimal("43.34")
    assert forecast[0].down_payment_details[0].original_date == date(2026, 1, 3)
    assert forecast[0].down_payment_details[0].overdue is True
    obligation.down_payment_paid = True
    paid_forecast = build_forecast(
        monthly_income=Decimal("1000.00"), fixed_expenses=Decimal("0.00"),
        obligations=[obligation], start_month=date(2026, 1, 15), months=1,
    )
    assert paid_forecast[0].down_payment_payments == Decimal("0.00")


def test_api_plan_schedule_compatibility_update_and_ownership(plan_client):
    client, db, auth, user_id = plan_client
    payload = {
        "provider": "valU", "item_name": "Laptop", "category": "Electronics",
        "purchase_price": "1000.00", "payment_method": "automatic", "interest_method": "reducing_balance",
        "nominal_annual_interest_rate": "10.0000", "down_payment_amount": "100.00",
        "down_payment_date": "2026-01-03", "down_payment_paid": False,
        "start_date": "2026-01-15", "term_months": 3, "due_day_of_month": 31,
    }
    response = client.post("/obligations/installment-plans", json=payload, headers={"Authorization": auth})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["purchase_price"] == "1000.00"
    assert body["total_amount"] == "1000.00"
    assert body["monthly_installment_amount"] == "305.01"
    assert body["schedule_version"] == 1
    obligation_id = body["id"]
    projected = client.get(
        "/forecast", params={"start_month": "2026-01-01", "months": 3},
        headers={"Authorization": auth},
    )
    assert projected.status_code == 200
    assert projected.json()["rows"][0]["installment_payments"] == "305.01"
    assert projected.json()["rows"][0]["down_payment_payments"] == "100.00"
    assert projected.json()["rows"][0]["obligation_payments"] == "405.01"
    assert projected.json()["rows"][0]["down_payment_details"] == [
        {"obligation_id": obligation_id, "original_date": "2026-01-03", "amount": "100.00", "overdue": False}
    ]
    schedule_response = client.get(f"/obligations/{obligation_id}/installments", headers={"Authorization": auth})
    assert schedule_response.status_code == 200
    rows = schedule_response.json()["installments"]
    assert [row["due_date"] for row in rows] == ["2026-01-31", "2026-02-28", "2026-03-31"]
    assert sum((Decimal(row["scheduled_amount"]) for row in rows), Decimal("0")) == Decimal("915.04")
    assert rows[-1]["interest_amount"] is not None

    update_payload = payload | {"schedule_version": 1, "nominal_annual_interest_rate": "11.0000"}
    updated = client.put(f"/obligations/{obligation_id}/installment-plan", json=update_payload, headers={"Authorization": auth})
    assert updated.status_code == 200, updated.text
    assert updated.json()["schedule_version"] == 2
    stale = client.put(f"/obligations/{obligation_id}/installment-plan", json=update_payload, headers={"Authorization": auth})
    assert stale.status_code == 409

    other = User(name="Other", email="other@example.test", password_hash="unused")
    db.add(other)
    db.commit()
    other_token = create_access_token(subject=str(other.id))
    hidden = client.get(f"/obligations/{obligation_id}/installments", headers={"Authorization": f"Bearer {other_token}"})
    assert hidden.status_code == 404
    stored = db.scalar(select(Obligation).where(Obligation.id == obligation_id))
    assert stored is not None and len(stored.installments) == 3 and stored.user_id == user_id


def test_plan_api_rejects_full_down_payment_with_422(plan_client):
    client, _db, auth, _user_id = plan_client
    response = client.post(
        "/obligations/installment-plans",
        json={
            "provider": "p", "item_name": "i", "category": "c", "purchase_price": "100.00",
            "payment_method": "manual", "monthly_installment_amount": "10.00",
            "down_payment_amount": "100.00", "down_payment_date": "2026-01-01",
            "start_date": "2026-01-01", "term_months": 1, "due_day_of_month": 1,
        },
        headers={"Authorization": auth},
    )
    assert response.status_code == 422
    assert "less than the purchase price" in str(response.json())


def test_dashboard_totals_use_persisted_schedule_and_overdue_down_payment(plan_client):
    client, _db, auth, _user_id = plan_client
    today = date.today()
    current_month = date(today.year, today.month, 1)
    overdue_date = current_month - timedelta(days=1)
    created = client.post(
        "/obligations/installment-plans",
        headers={"Authorization": auth},
        json={
            "provider": "provider", "item_name": "item", "category": "other",
            "purchase_price": "1000.00", "payment_method": "automatic", "interest_method": "none",
            "down_payment_amount": "100.00", "down_payment_date": overdue_date.isoformat(),
            "start_date": current_month.isoformat(), "term_months": 3, "due_day_of_month": 15,
        },
    )
    assert created.status_code == 201, created.text

    dashboard = client.get("/dashboard/summary", headers={"Authorization": auth})
    assert dashboard.status_code == 200, dashboard.text
    body = dashboard.json()
    assert body["current_month_installment_payments"] == "300.00"
    assert body["current_month_down_payment_payments"] == "100.00"
    assert body["current_month_overdue_down_payment_payments"] == "100.00"
    assert body["current_month_obligation_payments"] == "400.00"
    assert body["current_month_down_payment_details"] == [
        {
            "obligation_id": created.json()["id"],
            "original_date": overdue_date.isoformat(),
            "amount": "100.00",
            "overdue": True,
        }
    ]


def test_legacy_conversion_requires_confirmation_and_preserves_status(plan_client):
    client, db, auth, user_id = plan_client
    legacy = Obligation(
        user_id=user_id, provider="old-provider", item_name="Old item", category="other",
        total_amount=Decimal("1200.00"), monthly_installment_amount=Decimal("100.00"),
        start_date=date(2026, 1, 1), term_months=12, due_day_of_month=1, status="late",
    )
    db.add(legacy)
    db.commit()
    db.refresh(legacy)
    payload = {
        "provider": "old-provider", "item_name": "Old item", "category": "other",
        "purchase_price": "1200.00", "payment_method": "automatic", "interest_method": "none",
        "start_date": "2026-01-01", "term_months": 12, "due_day_of_month": 1,
    }
    refused = client.post(
        f"/obligations/{legacy.id}/convert-to-installment-plan",
        json=payload | {"confirm_conversion": False}, headers={"Authorization": auth},
    )
    assert refused.status_code == 422
    converted = client.post(
        f"/obligations/{legacy.id}/convert-to-installment-plan",
        json=payload | {"confirm_conversion": True}, headers={"Authorization": auth},
    )
    assert converted.status_code == 200, converted.text
    assert converted.json()["status"] == "late"
    assert converted.json()["total_amount"] == "1200.00"
    assert converted.json()["schedule_version"] == 1


def test_plan_aware_affordability_uses_schedule_and_down_payment(plan_client):
    client, db, auth, user_id = plan_client
    user = db.scalar(select(User).where(User.id == user_id))
    user.monthly_income = Decimal("2000.00")
    user.fixed_expenses = Decimal("100.00")
    db.commit()
    response = client.post(
        "/affordability",
        headers={"Authorization": auth},
        json={
            "purchase_price": "1000.00", "payment_method": "automatic", "interest_method": "none",
            "down_payment_amount": "100.00", "down_payment_date": "2026-01-03",
            "start_date": "2026-01-15", "term_months": 3, "due_day_of_month": 15,
        },
    )
    assert response.status_code == 200, response.text
    rows = response.json()["monthly_results"]
    assert len(rows) == 3
    assert rows[0]["proposed_installment_amount"] == "300.00"
    assert rows[0]["proposed_down_payment_amount"] == "100.00"
    assert rows[0]["proposed_commitment_amount"] == "400.00"
    assert rows[1]["proposed_commitment_amount"] == "300.00"
