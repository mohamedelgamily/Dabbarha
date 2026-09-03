from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import create_access_token, decode_access_token, verify_password
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
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert isinstance(data["id"], int)
    assert data["name"] == "Nour Hassan"
    assert data["email"] == "nour@example.com"
    assert Decimal(str(data["monthly_income"])) == Decimal("0.00")
    assert Decimal(str(data["fixed_expenses"])) == Decimal("0.00")
    assert data["currency"] == "EGP"
    assert "created_at" in data
    assert data["created_at"] is not None


@pytest.mark.parametrize(
    "financial_field,value",
    [
        ("monthly_income", "25000.00"),
        ("fixed_expenses", "7500.50"),
        ("currency", "EGP"),
    ],
)
def test_registration_rejects_financial_fields(
    client: TestClient, financial_field: str, value: str
) -> None:
    payload = {
        "name": "Nour Hassan",
        "email": f"nour.{financial_field}@example.com",
        "password": "StrongPassword123!",
        financial_field: value,
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422


def test_password_is_never_returned(client: TestClient) -> None:
    payload = {
        "name": "Nour Hassan",
        "email": "nour.security@example.com",
        "password": "SuperSecretPassword123!",
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
    }
    first_response = client.post("/auth/register", json=payload)
    assert first_response.status_code == 201

    duplicate_payload = {
        "name": "Second User",
        "email": "DUPLICATE@example.com",
        "password": "DifferentPassword456!",
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
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("missing_field", ["name", "email", "password"])
def test_missing_required_fields_rejected(client: TestClient, missing_field: str) -> None:
    payload = {
        "name": "Complete Name",
        "email": "complete@example.com",
        "password": "Password123!",
    }
    payload.pop(missing_field)
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422


def test_default_currency_applied(client: TestClient, db_session: Session) -> None:
    payload = {
        "name": "Default Currency User",
        "email": "default.currency@example.com",
        "password": "Password123!",
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
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == 201

    login_payload = {
        "email": "nour.fin@example.com",
        "password": "SecretPassword123!",
    }
    login_response = client.post("/auth/login", json=login_payload)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Set financial values via PATCH /auth/me
    patch_response = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "monthly_income": "35000.00",
            "fixed_expenses": "12000.00",
        },
    )
    assert patch_response.status_code == 200

    # New login token still does not include financial fields
    second_login = client.post("/auth/login", json=login_payload)
    assert second_login.status_code == 200
    token2 = second_login.json()["access_token"]

    payload = decode_access_token(token2)
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


def test_get_current_user_profile_success(client: TestClient) -> None:
    register_payload = {
        "name": "Nour Profile",
        "email": "nour.profile@example.com",
        "password": "CorrectPassword123!",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == 201
    registered_data = reg_response.json()
    assert Decimal(str(registered_data["monthly_income"])) == Decimal("0.00")
    assert Decimal(str(registered_data["fixed_expenses"])) == Decimal("0.00")
    assert registered_data["currency"] == "EGP"

    login_payload = {
        "email": "nour.profile@example.com",
        "password": "CorrectPassword123!",
    }
    login_response = client.post("/auth/login", json=login_payload)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Initial GET /auth/me returns default financial fields
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == registered_data["id"]
    assert data["name"] == "Nour Profile"
    assert data["email"] == "nour.profile@example.com"
    assert Decimal(str(data["monthly_income"])) == Decimal("0.00")
    assert Decimal(str(data["fixed_expenses"])) == Decimal("0.00")
    assert data["currency"] == "EGP"
    assert "created_at" in data
    assert "password" not in data
    assert "password_hash" not in data

    # Update profile optionally via PATCH /auth/me
    patch_response = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "monthly_income": "30000.00",
            "fixed_expenses": "8000.00",
            "currency": "USD",
        },
    )
    assert patch_response.status_code == 200

    # GET /auth/me returns updated financial fields
    updated_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert updated_response.status_code == 200
    updated_data = updated_response.json()
    assert Decimal(str(updated_data["monthly_income"])) == Decimal("30000.00")
    assert Decimal(str(updated_data["fixed_expenses"])) == Decimal("8000.00")
    assert updated_data["currency"] == "USD"


def test_get_current_user_missing_authorization_header(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_get_current_user_invalid_malformed_token(client: TestClient) -> None:
    response = client.get("/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_get_current_user_expired_token(client: TestClient) -> None:
    register_payload = {
        "name": "Nour Expired",
        "email": "nour.expired@example.com",
        "password": "CorrectPassword123!",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == 201
    user_id = reg_response.json()["id"]

    expired_token = create_access_token(
        subject=str(user_id),
        expires_delta=timedelta(seconds=-1),
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_get_current_user_nonexistent_user(client: TestClient) -> None:
    token = create_access_token(subject="999999")
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_get_current_user_invalid_subject(client: TestClient) -> None:
    token = create_access_token(subject="not-an-integer-id")
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_get_current_user_excludes_password_and_hash(client: TestClient) -> None:
    register_payload = {
        "name": "Nour SecurityCheck",
        "email": "nour.securitycheck@example.com",
        "password": "CorrectPassword123!",
    }
    reg_response = client.post("/auth/register", json=register_payload)
    assert reg_response.status_code == 201

    login_payload = {
        "email": "nour.securitycheck@example.com",
        "password": "CorrectPassword123!",
    }
    login_response = client.post("/auth/login", json=login_payload)
    token = login_response.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert "password" not in data
    assert "password_hash" not in data


def _register_and_get_token(client: TestClient, email: str = "patch.user@example.com") -> str:
    reg_response = client.post(
        "/auth/register",
        json={"name": "Patch User", "email": email, "password": "Password123!"},
    )
    assert reg_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_response.status_code == 200
    return login_response.json()["access_token"]


def test_patch_me_updates_monthly_income(client: TestClient) -> None:
    token = _register_and_get_token(client, email="income.update@example.com")

    patch_response = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"monthly_income": "12500.75"},
    )
    assert patch_response.status_code == 200
    data = patch_response.json()
    assert Decimal(str(data["monthly_income"])) == Decimal("12500.75")
    assert Decimal(str(data["fixed_expenses"])) == Decimal("0.00")
    assert data["currency"] == "EGP"

    get_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert get_response.status_code == 200
    assert Decimal(str(get_response.json()["monthly_income"])) == Decimal("12500.75")


def test_patch_me_updates_fixed_expenses(client: TestClient) -> None:
    token = _register_and_get_token(client, email="expenses.update@example.com")

    patch_response = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"fixed_expenses": "4321.50"},
    )
    assert patch_response.status_code == 200
    data = patch_response.json()
    assert Decimal(str(data["monthly_income"])) == Decimal("0.00")
    assert Decimal(str(data["fixed_expenses"])) == Decimal("4321.50")
    assert data["currency"] == "EGP"

    get_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert get_response.status_code == 200
    assert Decimal(str(get_response.json()["fixed_expenses"])) == Decimal("4321.50")


def test_patch_me_updates_currency(client: TestClient) -> None:
    token = _register_and_get_token(client, email="currency.update@example.com")

    patch_response = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"currency": "SAR"},
    )
    assert patch_response.status_code == 200
    data = patch_response.json()
    assert Decimal(str(data["monthly_income"])) == Decimal("0.00")
    assert Decimal(str(data["fixed_expenses"])) == Decimal("0.00")
    assert data["currency"] == "SAR"

    get_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert get_response.status_code == 200
    assert get_response.json()["currency"] == "SAR"


def test_patch_me_partial_updates_preserve_omitted_fields(client: TestClient) -> None:
    token = _register_and_get_token(client, email="partial.update@example.com")

    # First update: set monthly_income
    r1 = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"monthly_income": "20000.00"},
    )
    assert r1.status_code == 200
    assert Decimal(str(r1.json()["monthly_income"])) == Decimal("20000.00")
    assert Decimal(str(r1.json()["fixed_expenses"])) == Decimal("0.00")
    assert r1.json()["currency"] == "EGP"

    # Second update: set fixed_expenses only
    r2 = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"fixed_expenses": "5000.00"},
    )
    assert r2.status_code == 200
    assert Decimal(str(r2.json()["monthly_income"])) == Decimal("20000.00")
    assert Decimal(str(r2.json()["fixed_expenses"])) == Decimal("5000.00")
    assert r2.json()["currency"] == "EGP"

    # Third update: set currency only
    r3 = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"currency": "EUR"},
    )
    assert r3.status_code == 200
    assert Decimal(str(r3.json()["monthly_income"])) == Decimal("20000.00")
    assert Decimal(str(r3.json()["fixed_expenses"])) == Decimal("5000.00")
    assert r3.json()["currency"] == "EUR"

    # Fourth update: update monthly_income only, ensure fixed_expenses and currency remain
    r4 = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"monthly_income": "25000.00"},
    )
    assert r4.status_code == 200
    assert Decimal(str(r4.json()["monthly_income"])) == Decimal("25000.00")
    assert Decimal(str(r4.json()["fixed_expenses"])) == Decimal("5000.00")
    assert r4.json()["currency"] == "EUR"


def test_patch_me_negative_monthly_income_rejected(client: TestClient) -> None:
    token = _register_and_get_token(client, email="negative.inc@example.com")
    response = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"monthly_income": "-500.00"},
    )
    assert response.status_code == 422


def test_patch_me_negative_fixed_expenses_rejected(client: TestClient) -> None:
    token = _register_and_get_token(client, email="negative.exp@example.com")
    response = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"fixed_expenses": "-100.00"},
    )
    assert response.status_code == 422


def test_patch_me_unauthenticated_returns_401(client: TestClient) -> None:
    response = client.patch("/auth/me", json={"monthly_income": "10000.00"})
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_patch_me_normalizes_currency(client: TestClient) -> None:
    token = _register_and_get_token(client, email="normalize.curr@example.com")

    # Lowercase with whitespace
    response = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"currency": "  usd  "},
    )
    assert response.status_code == 200
    assert response.json()["currency"] == "USD"

    # Lowercase without whitespace
    response2 = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"currency": "eur"},
    )
    assert response2.status_code == 200
    assert response2.json()["currency"] == "EUR"


@pytest.mark.parametrize("invalid_currency", ["", "   ", "USDD", "EGPP"])
def test_patch_me_rejects_invalid_currency(client: TestClient, invalid_currency: str) -> None:
    token = _register_and_get_token(client, email="invalid.curr@example.com")
    response = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"currency": invalid_currency},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("field_name", ["monthly_income", "fixed_expenses", "currency"])
def test_patch_me_rejects_null_values(client: TestClient, field_name: str) -> None:
    token = _register_and_get_token(client, email=f"null.{field_name}@example.com")
    response = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={field_name: None},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "disallowed_field,value",
    [
        ("id", 123),
        ("email", "hacker@example.com"),
        ("password", "HackedPassword123!"),
        ("password_hash", "some-hashed-password"),
        ("created_at", "2020-01-01T00:00:00Z"),
        ("name", "New Name"),
    ],
)
def test_patch_me_rejects_identity_and_immutable_fields(
    client: TestClient, disallowed_field: str, value: object
) -> None:
    token = _register_and_get_token(client, email=f"immutable.{disallowed_field}@example.com")
    response = client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={disallowed_field: value},
    )
    assert response.status_code == 422


def test_obligation_creation_does_not_require_financial_information(
    client: TestClient,
) -> None:
    reg_response = client.post(
        "/auth/register",
        json={
            "name": "Zero Finance User",
            "email": "zero.finance@example.com",
            "password": "Password123!",
        },
    )
    assert reg_response.status_code == 201
    assert Decimal(str(reg_response.json()["monthly_income"])) == Decimal("0.00")
    assert Decimal(str(reg_response.json()["fixed_expenses"])) == Decimal("0.00")

    login_response = client.post(
        "/auth/login",
        json={"email": "zero.finance@example.com", "password": "Password123!"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Creating an obligation must succeed without any financial inputs configured
    obligation_payload = {
        "provider": "valU",
        "item_name": "Phone Installment",
        "category": "Electronics",
        "total_amount": "12000.00",
        "monthly_installment_amount": "1000.00",
        "start_date": "2026-01-01",
        "term_months": 12,
        "due_day_of_month": 10,
    }
    create_response = client.post(
        "/obligations",
        json=obligation_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_response.status_code == 201
    data = create_response.json()
    assert data["item_name"] == "Phone Installment"
    assert Decimal(str(data["monthly_installment_amount"])) == Decimal("1000.00")
