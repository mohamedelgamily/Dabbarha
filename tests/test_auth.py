from collections.abc import Generator
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import decode_access_token, verify_password
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


def test_successful_login(client: TestClient) -> None:
    register_payload = {
        "name": "Nour Login",
        "email": "nour.login@example.com",
        "password": "CorrectPassword123!",
        "monthly_income": "20000.00",
        "fixed_expenses": "5000.00",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == 201

    login_payload = {
        "email": "nour.login@example.com",
        "password": "CorrectPassword123!",
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 0
    assert data["token_type"] == "bearer"


def test_login_jwt_can_be_decoded_and_identifies_user(client: TestClient) -> None:
    register_payload = {
        "name": "Nour Decodable",
        "email": "nour.jwt@example.com",
        "password": "CorrectPassword123!",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == 201
    user_id = reg_response.json()["id"]

    login_payload = {
        "email": "nour.jwt@example.com",
        "password": "CorrectPassword123!",
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 200
    token = response.json()["access_token"]

    payload = decode_access_token(token)
    assert "sub" in payload
    assert "exp" in payload
    assert payload["sub"] == str(user_id)


def test_login_jwt_expiration(client: TestClient) -> None:
    register_payload = {
        "name": "Nour Expiration",
        "email": "nour.exp@example.com",
        "password": "CorrectPassword123!",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == 201

    login_payload = {
        "email": "nour.exp@example.com",
        "password": "CorrectPassword123!",
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 200
    token = response.json()["access_token"]

    payload = decode_access_token(token)
    assert "exp" in payload
    now_timestamp = datetime.now(timezone.utc).timestamp()
    assert payload["exp"] > now_timestamp


def test_login_wrong_password_rejected(client: TestClient) -> None:
    register_payload = {
        "name": "Nour WrongPW",
        "email": "nour.wrongpw@example.com",
        "password": "CorrectPassword123!",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == 201

    login_payload = {
        "email": "nour.wrongpw@example.com",
        "password": "IncorrectPassword456!",
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert response.headers.get("www-authenticate") == "Bearer"


def test_login_unknown_email_rejected(client: TestClient) -> None:
    login_payload = {
        "email": "nonexistent.user@example.com",
        "password": "SomePassword123!",
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert response.headers.get("www-authenticate") == "Bearer"


def test_login_response_does_not_contain_password_or_hash(client: TestClient) -> None:
    register_payload = {
        "name": "Nour Sanitized",
        "email": "nour.sanitized@example.com",
        "password": "SecretPassword123!",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == 201

    login_payload = {
        "email": "nour.sanitized@example.com",
        "password": "SecretPassword123!",
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert "password" not in data
    assert "password_hash" not in data


def test_login_jwt_does_not_contain_sensitive_financial_data(client: TestClient) -> None:
    register_payload = {
        "name": "Nour Financials",
        "email": "nour.fin@example.com",
        "password": "SecretPassword123!",
        "monthly_income": "35000.00",
        "fixed_expenses": "12000.00",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == 201

    login_payload = {
        "email": "nour.fin@example.com",
        "password": "SecretPassword123!",
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 200
    token = response.json()["access_token"]

    payload = decode_access_token(token)
    assert "monthly_income" not in payload
    assert "fixed_expenses" not in payload
    assert "obligations" not in payload
    assert "password" not in payload
    assert "password_hash" not in payload
    assert "email" not in payload
    assert "name" not in payload
    assert set(payload.keys()) == {"sub", "exp"}


@pytest.mark.parametrize("invalid_email", ["not-an-email", "@missinguser.com", "plainaddress", "missing@domain"])
def test_login_invalid_email_rejected(client: TestClient, invalid_email: str) -> None:
    payload = {
        "email": invalid_email,
        "password": "Password123!",
    }
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 422


def test_login_missing_password_rejected(client: TestClient) -> None:
    payload = {
        "email": "user@example.com",
    }
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 422


def test_login_missing_email_rejected(client: TestClient) -> None:
    payload = {
        "password": "Password123!",
    }
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 422


def test_login_email_normalized(client: TestClient) -> None:
    register_payload = {
        "name": "Nour Normalize",
        "email": "nour.normalize@example.com",
        "password": "Password123!",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == 201

    login_payload = {
        "email": "  NOUR.NORMALIZE@EXAMPLE.COM  ",
        "password": "Password123!",
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
