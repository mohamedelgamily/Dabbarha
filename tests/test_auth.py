from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import verify_password
from app.db.database import Base
from app.main import app
from app.models.user import User


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


def test_successful_registration(client: TestClient) -> None:
    payload = {
        "name": "Nour Hassan",
        "email": "nour@example.com",
        "password": "StrongPassword123!",
        "monthly_income": "25000.00",
        "fixed_expenses": "7500.50",
        "currency": "EGP",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert isinstance(data["id"], int)
    assert data["name"] == "Nour Hassan"
    assert data["email"] == "nour@example.com"
    assert Decimal(str(data["monthly_income"])) == Decimal("25000.00")
    assert Decimal(str(data["fixed_expenses"])) == Decimal("7500.50")
    assert data["currency"] == "EGP"
    assert "created_at" in data
    assert data["created_at"] is not None


def test_password_is_never_returned(client: TestClient) -> None:
    payload = {
        "name": "Nour Hassan",
        "email": "nour.security@example.com",
        "password": "SuperSecretPassword123!",
        "monthly_income": "15000.00",
        "fixed_expenses": "3000.00",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "password" not in data
    assert "password_hash" not in data


def test_password_is_actually_hashed(client: TestClient, db_session: Session) -> None:
    raw_password = "MySecurePassword999!"
    payload = {
        "name": "Hashed User",
        "email": "hashed@example.com",
        "password": raw_password,
        "monthly_income": "10000.00",
        "fixed_expenses": "2000.00",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201

    user_in_db = db_session.scalar(select(User).where(User.email == "hashed@example.com"))
    assert user_in_db is not None
    assert user_in_db.password_hash != raw_password
    assert verify_password(raw_password, user_in_db.password_hash) is True


def test_duplicate_email_rejected(client: TestClient) -> None:
    payload = {
        "name": "First User",
        "email": "duplicate@example.com",
        "password": "Password123!",
        "monthly_income": "10000.00",
        "fixed_expenses": "2000.00",
    }
    first_response = client.post("/auth/register", json=payload)
    assert first_response.status_code == 201

    duplicate_payload = {
        "name": "Second User",
        "email": "DUPLICATE@example.com",
        "password": "DifferentPassword456!",
        "monthly_income": "12000.00",
        "fixed_expenses": "3000.00",
    }
    duplicate_response = client.post("/auth/register", json=duplicate_payload)
    assert duplicate_response.status_code == 409
    assert "already exists" in duplicate_response.json()["detail"].lower()


@pytest.mark.parametrize("invalid_email", ["not-an-email", "@missinguser.com", "plainaddress", "missing@domain"])
def test_invalid_email_rejected(client: TestClient, invalid_email: str) -> None:
    payload = {
        "name": "Invalid Email User",
        "email": invalid_email,
        "password": "Password123!",
        "monthly_income": "10000.00",
        "fixed_expenses": "2000.00",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422


def test_negative_monthly_income_rejected(client: TestClient) -> None:
    payload = {
        "name": "Negative Income User",
        "email": "negative.income@example.com",
        "password": "Password123!",
        "monthly_income": "-500.00",
        "fixed_expenses": "2000.00",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422


def test_negative_fixed_expenses_rejected(client: TestClient) -> None:
    payload = {
        "name": "Negative Expenses User",
        "email": "negative.expenses@example.com",
        "password": "Password123!",
        "monthly_income": "10000.00",
        "fixed_expenses": "-100.00",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("missing_field", ["name", "email", "password"])
def test_missing_required_fields_rejected(client: TestClient, missing_field: str) -> None:
    payload = {
        "name": "Complete Name",
        "email": "complete@example.com",
        "password": "Password123!",
        "monthly_income": "10000.00",
        "fixed_expenses": "2000.00",
    }
    payload.pop(missing_field)
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422


def test_default_currency_applied(client: TestClient, db_session: Session) -> None:
    payload = {
        "name": "Default Currency User",
        "email": "default.currency@example.com",
        "password": "Password123!",
        "monthly_income": "10000.00",
        "fixed_expenses": "2000.00",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201
    assert response.json()["currency"] == "EGP"

    user_in_db = db_session.scalar(
        select(User).where(User.email == "default.currency@example.com")
    )
    assert user_in_db is not None
    assert user_in_db.currency == "EGP"


def test_health_endpoint_still_works(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
