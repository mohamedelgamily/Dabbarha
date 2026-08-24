from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import create_access_token
from app.db.database import Base
from app.main import app
from app.models.obligation import Obligation
from app.models.user import User
from app.schemas.obligation import ObligationCreate, ObligationResponse


# ==============================================================================
# Schema Unit Tests
# ==============================================================================

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


# ==============================================================================
# API Integration Tests (POST /obligations)
# ==============================================================================

@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_create_obligation_success(client: TestClient, db_session: Session) -> None:
    # Register and login a user
    register_payload = {
        "name": "Mariam Karim",
        "email": "mariam@example.com",
        "password": "Password123!",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == 201
    user_id = reg_response.json()["id"]

    login_response = client.post(
        "/auth/login",
        json={"email": "mariam@example.com", "password": "Password123!"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    obligation_payload = {
        "provider": "valU",
        "item_name": "iPhone 15 Pro",
        "category": "Electronics",
        "total_amount": "36000.00",
        "monthly_installment_amount": "3000.00",
        "start_date": "2026-02-01",
        "term_months": 12,
        "due_day_of_month": 10,
        "status": "active",
        "source": "manual_entry",
    }

    response = client.post(
        "/obligations",
        json=obligation_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()

    assert isinstance(data["id"], int)
    assert data["user_id"] == user_id
    assert data["provider"] == "valU"
    assert data["item_name"] == "iPhone 15 Pro"
    assert data["category"] == "Electronics"
    assert Decimal(str(data["total_amount"])) == Decimal("36000.00")
    assert Decimal(str(data["monthly_installment_amount"])) == Decimal("3000.00")
    assert data["start_date"] == "2026-02-01"
    assert data["term_months"] == 12
    assert data["due_day_of_month"] == 10
    assert data["status"] == "active"
    assert data["source"] == "manual_entry"
    assert "created_at" in data
    assert "updated_at" in data

    # Verify directly in DB
    db_obligation = db_session.scalar(
        select(Obligation).where(Obligation.id == data["id"])
    )
    assert db_obligation is not None
    assert db_obligation.user_id == user_id
    assert db_obligation.provider == "valU"
    assert db_obligation.item_name == "iPhone 15 Pro"
    assert db_obligation.total_amount == Decimal("36000.00")


def test_create_obligation_unauthenticated_rejected(client: TestClient) -> None:
    obligation_payload = {
        "provider": "valU",
        "item_name": "iPhone 15 Pro",
        "category": "Electronics",
        "total_amount": "36000.00",
        "monthly_installment_amount": "3000.00",
        "start_date": "2026-02-01",
        "term_months": 12,
        "due_day_of_month": 10,
    }
    response = client.post("/obligations", json=obligation_payload)
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_create_obligation_invalid_token_rejected(client: TestClient) -> None:
    obligation_payload = {
        "provider": "valU",
        "item_name": "iPhone 15 Pro",
        "category": "Electronics",
        "total_amount": "36000.00",
        "monthly_installment_amount": "3000.00",
        "start_date": "2026-02-01",
        "term_months": 12,
        "due_day_of_month": 10,
    }
    response = client.post(
        "/obligations",
        json=obligation_payload,
        headers={"Authorization": "Bearer invalid.token.value"},
    )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_create_obligation_expired_token_rejected(client: TestClient) -> None:
    expired_token = create_access_token(subject="1", expires_delta=timedelta(seconds=-1))
    obligation_payload = {
        "provider": "valU",
        "item_name": "iPhone 15 Pro",
        "category": "Electronics",
        "total_amount": "36000.00",
        "monthly_installment_amount": "3000.00",
        "start_date": "2026-02-01",
        "term_months": 12,
        "due_day_of_month": 10,
    }
    response = client.post(
        "/obligations",
        json=obligation_payload,
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_create_obligation_client_cannot_spoof_user_id(client: TestClient) -> None:
    # Register and login user
    reg_response = client.post(
        "/auth/register",
        json={"name": "Real Owner", "email": "owner@example.com", "password": "Password123!"},
    )
    assert reg_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "Password123!"},
    )
    token = login_response.json()["access_token"]

    spoofed_payload = {
        "user_id": 9999,
        "provider": "valU",
        "item_name": "Smart TV",
        "category": "Electronics",
        "total_amount": "12000.00",
        "monthly_installment_amount": "1000.00",
        "start_date": "2026-01-01",
        "term_months": 12,
        "due_day_of_month": 1,
    }
    response = client.post(
        "/obligations",
        json=spoofed_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    # Pydantic extra="forbid" rejects extra fields
    assert response.status_code == 422


def test_created_obligation_belongs_to_authenticated_user_isolation(
    client: TestClient, db_session: Session
) -> None:
    # Register User A
    reg_a = client.post(
        "/auth/register",
        json={"name": "User A", "email": "usera@example.com", "password": "Password123!"},
    )
    user_a_id = reg_a.json()["id"]
    login_a = client.post(
        "/auth/login",
        json={"email": "usera@example.com", "password": "Password123!"},
    )
    token_a = login_a.json()["access_token"]

    # Register User B
    reg_b = client.post(
        "/auth/register",
        json={"name": "User B", "email": "userb@example.com", "password": "Password123!"},
    )
    user_b_id = reg_b.json()["id"]

    # Create obligation as User A
    obligation_payload = {
        "provider": "aman",
        "item_name": "Laptop",
        "category": "Electronics",
        "total_amount": "20000.00",
        "monthly_installment_amount": "2000.00",
        "start_date": "2026-03-01",
        "term_months": 10,
        "due_day_of_month": 15,
    }
    response = client.post(
        "/obligations",
        json=obligation_payload,
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 201
    created_id = response.json()["id"]

    # Check database isolation
    db_user_a = db_session.get(User, user_a_id)
    db_user_b = db_session.get(User, user_b_id)
    assert db_user_a is not None
    assert db_user_b is not None

    user_a_obligation_ids = [ob.id for ob in db_user_a.obligations]
    user_b_obligation_ids = [ob.id for ob in db_user_b.obligations]

    assert created_id in user_a_obligation_ids
    assert created_id not in user_b_obligation_ids
    assert len(user_b_obligation_ids) == 0


@pytest.mark.parametrize(
    "invalid_field,invalid_value",
    [
        ("total_amount", "-100.00"),
        ("monthly_installment_amount", "-50.00"),
        ("term_months", 0),
        ("term_months", -5),
        ("due_day_of_month", 0),
        ("due_day_of_month", 32),
        ("status", "invalid_status"),
        ("source", "invalid_source"),
    ],
)
def test_create_obligation_validation_failures_via_api(
    client: TestClient, invalid_field: str, invalid_value: object
) -> None:
    reg_response = client.post(
        "/auth/register",
        json={"name": "Validation User", "email": "val@example.com", "password": "Password123!"},
    )
    login_response = client.post(
        "/auth/login",
        json={"email": "val@example.com", "password": "Password123!"},
    )
    token = login_response.json()["access_token"]

    payload: dict[str, object] = {
        "provider": "valU",
        "item_name": "TV",
        "category": "Electronics",
        "total_amount": "10000.00",
        "monthly_installment_amount": "1000.00",
        "start_date": "2026-01-01",
        "term_months": 10,
        "due_day_of_month": 5,
    }
    payload[invalid_field] = invalid_value

    response = client.post(
        "/obligations",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("missing_field", ["provider", "item_name", "category", "total_amount", "monthly_installment_amount", "start_date", "term_months", "due_day_of_month"])
def test_create_obligation_missing_required_fields_rejected(
    client: TestClient, missing_field: str
) -> None:
    reg_response = client.post(
        "/auth/register",
        json={"name": "Missing Field User", "email": "missing@example.com", "password": "Password123!"},
    )
    login_response = client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": "Password123!"},
    )
    token = login_response.json()["access_token"]

    payload: dict[str, object] = {
        "provider": "valU",
        "item_name": "TV",
        "category": "Electronics",
        "total_amount": "10000.00",
        "monthly_installment_amount": "1000.00",
        "start_date": "2026-01-01",
        "term_months": 10,
        "due_day_of_month": 5,
    }
    payload.pop(missing_field)

    response = client.post(
        "/obligations",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
