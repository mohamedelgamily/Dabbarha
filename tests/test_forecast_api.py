from collections.abc import Generator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import create_access_token
from app.db.database import Base
from app.main import app
from app.models.obligation import Obligation
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


def register_and_login(
    client: TestClient,
    *,
    name: str = "Forecast User",
    email: str = "forecast@example.com",
    monthly_income: str = "10000.00",
    fixed_expenses: str = "2500.00",
) -> tuple[int, str]:
    register_response = client.post(
        "/auth/register",
        json={
            "name": name,
            "email": email,
            "password": "Password123!",
            "monthly_income": monthly_income,
            "fixed_expenses": fixed_expenses,
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_response.status_code == 200

    return register_response.json()["id"], login_response.json()["access_token"]


def create_obligation(
    db_session: Session,
    *,
    user_id: int,
    monthly_installment_amount: Decimal = Decimal("1000.00"),
    start_date: date = date(2026, 1, 15),
    term_months: int = 3,
    status: str = "active",
) -> Obligation:
    obligation = Obligation(
        user_id=user_id,
        provider="valU",
        item_name="Laptop",
        category="Electronics",
        total_amount=Decimal("12000.00"),
        monthly_installment_amount=monthly_installment_amount,
        start_date=start_date,
        term_months=term_months,
        due_day_of_month=15,
        status=status,
    )
    db_session.add(obligation)
    db_session.commit()
    db_session.refresh(obligation)
    return obligation


def test_get_forecast_returns_authenticated_users_monthly_forecast(
    client: TestClient,
    db_session: Session,
) -> None:
    user_id, token = register_and_login(
        client,
        monthly_income="10000.00",
        fixed_expenses="2500.00",
    )
    create_obligation(
        db_session,
        user_id=user_id,
        monthly_installment_amount=Decimal("1000.00"),
        start_date=date(2026, 2, 20),
        term_months=2,
    )

    response = client.get(
        "/forecast",
        params={"start_month": "2026-01-15", "months": 4},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "rows": [
            {
                "month": "2026-01-01",
                "income": "10000.00",
                "fixed_expenses": "2500.00",
                "obligation_payments": "0.00",
                "projected_buffer": "7500.00",
                "has_negative_buffer": False,
            },
            {
                "month": "2026-02-01",
                "income": "10000.00",
                "fixed_expenses": "2500.00",
                "obligation_payments": "1000.00",
                "projected_buffer": "6500.00",
                "has_negative_buffer": False,
            },
            {
                "month": "2026-03-01",
                "income": "10000.00",
                "fixed_expenses": "2500.00",
                "obligation_payments": "1000.00",
                "projected_buffer": "6500.00",
                "has_negative_buffer": False,
            },
            {
                "month": "2026-04-01",
                "income": "10000.00",
                "fixed_expenses": "2500.00",
                "obligation_payments": "0.00",
                "projected_buffer": "7500.00",
                "has_negative_buffer": False,
            },
        ],
    }


def test_get_forecast_uses_only_authenticated_users_obligations(
    client: TestClient,
    db_session: Session,
) -> None:
    user_a_id, token_a = register_and_login(
        client,
        name="Forecast User A",
        email="forecast.a@example.com",
        monthly_income="5000.00",
        fixed_expenses="2000.00",
    )
    user_b_id, _token_b = register_and_login(
        client,
        name="Forecast User B",
        email="forecast.b@example.com",
        monthly_income="5000.00",
        fixed_expenses="2000.00",
    )
    create_obligation(
        db_session,
        user_id=user_a_id,
        monthly_installment_amount=Decimal("1000.00"),
    )
    create_obligation(
        db_session,
        user_id=user_b_id,
        monthly_installment_amount=Decimal("2500.00"),
    )

    response = client.get(
        "/forecast",
        params={"start_month": "2026-01-01", "months": 1},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["obligation_payments"] == "1000.00"
    assert row["projected_buffer"] == "2000.00"
    assert row["has_negative_buffer"] is False


def test_get_forecast_uses_current_user_income_and_fixed_expenses(
    client: TestClient,
) -> None:
    _user_id, token = register_and_login(
        client,
        monthly_income="6000.00",
        fixed_expenses="6000.00",
    )

    response = client.get(
        "/forecast",
        params={"start_month": "2026-01-01", "months": 1},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["income"] == "6000.00"
    assert row["fixed_expenses"] == "6000.00"
    assert row["projected_buffer"] == "0.00"


def test_get_forecast_rejects_non_window_query_parameters(client: TestClient) -> None:
    _user_id, token = register_and_login(client, email="forecast.extra@example.com")

    response = client.get(
        "/forecast",
        params={
            "start_month": "2026-01-01",
            "months": 1,
            "monthly_income": "99999.00",
            "fixed_expenses": "0.00",
            "user_id": 9999,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Only start_month and months query parameters are accepted"


def test_get_forecast_unauthenticated_returns_401(client: TestClient) -> None:
    response = client.get(
        "/forecast",
        params={"start_month": "2026-01-01", "months": 1},
    )

    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_get_forecast_invalid_token_returns_401(client: TestClient) -> None:
    response = client.get(
        "/forecast",
        params={"start_month": "2026-01-01", "months": 1},
        headers={"Authorization": "Bearer invalid.token.value"},
    )

    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_get_forecast_expired_token_returns_401(client: TestClient) -> None:
    expired_token = create_access_token(subject="1", expires_delta=timedelta(seconds=-1))

    response = client.get(
        "/forecast",
        params={"start_month": "2026-01-01", "months": 1},
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize(
    "params",
    [
        {"months": 1},
        {"start_month": "2026-01-01"},
        {"start_month": "not-a-date", "months": 1},
        {"start_month": "2026-01-01", "months": 0},
        {"start_month": "2026-01-01", "months": -1},
        {"start_month": "2026-01-01", "months": 61},
    ],
)
def test_get_forecast_invalid_parameters_return_422(
    client: TestClient,
    params: dict[str, object],
) -> None:
    _user_id, token = register_and_login(
        client,
        email=f"forecast.invalid.{len(str(params))}@example.com",
    )

    response = client.get(
        "/forecast",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_get_forecast_does_not_mutate_obligations(
    client: TestClient,
    db_session: Session,
) -> None:
    user_id, token = register_and_login(client, email="forecast.readonly@example.com")
    obligation = create_obligation(db_session, user_id=user_id)

    response = client.get(
        "/forecast",
        params={"start_month": "2026-01-01", "months": 2},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    db_session.expire_all()
    unchanged = db_session.scalar(select(Obligation).where(Obligation.id == obligation.id))
    assert unchanged is not None
    assert unchanged.monthly_installment_amount == Decimal("1000.00")
    assert unchanged.status == "active"
