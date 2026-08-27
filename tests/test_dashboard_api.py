from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.forecast import add_months, month_start
from app.db.database import Base
from app.main import app
from app.models.obligation import Obligation


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
    name: str = "Dashboard User",
    email: str = "dashboard@example.com",
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
    start_date: date | None = None,
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
        start_date=start_date or current_month_start(),
        term_months=term_months,
        due_day_of_month=15,
        status=status,
    )
    db_session.add(obligation)
    db_session.commit()
    db_session.refresh(obligation)
    return obligation


def current_month_start() -> date:
    return month_start(date.today())


def test_get_dashboard_summary_authenticated_success(
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
    )

    response = client.get(
        "/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "monthly_income": "10000.00",
        "fixed_expenses": "2500.00",
        "current_month_obligation_payments": "1000.00",
        "current_month_projected_buffer": "6500.00",
        "has_current_month_negative_buffer": False,
        "active_obligations_count": 1,
    }


def test_get_dashboard_summary_unauthenticated_returns_401(client: TestClient) -> None:
    response = client.get("/dashboard/summary")

    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_get_dashboard_summary_uses_only_authenticated_users_obligations(
    client: TestClient,
    db_session: Session,
) -> None:
    user_a_id, token_a = register_and_login(
        client,
        name="Dashboard User A",
        email="dashboard.a@example.com",
        monthly_income="5000.00",
        fixed_expenses="2000.00",
    )
    user_b_id, _token_b = register_and_login(
        client,
        name="Dashboard User B",
        email="dashboard.b@example.com",
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
        "/dashboard/summary",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["current_month_obligation_payments"] == "1000.00"
    assert data["current_month_projected_buffer"] == "2000.00"
    assert data["active_obligations_count"] == 1


def test_get_dashboard_summary_with_no_obligations(client: TestClient) -> None:
    _user_id, token = register_and_login(
        client,
        email="dashboard.none@example.com",
        monthly_income="8000.00",
        fixed_expenses="3000.00",
    )

    response = client.get(
        "/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "monthly_income": "8000.00",
        "fixed_expenses": "3000.00",
        "current_month_obligation_payments": "0.00",
        "current_month_projected_buffer": "5000.00",
        "has_current_month_negative_buffer": False,
        "active_obligations_count": 0,
    }


def test_get_dashboard_summary_sums_multiple_current_month_obligations(
    client: TestClient,
    db_session: Session,
) -> None:
    user_id, token = register_and_login(
        client,
        email="dashboard.multiple@example.com",
        monthly_income="9000.00",
        fixed_expenses="2500.00",
    )
    create_obligation(
        db_session,
        user_id=user_id,
        monthly_installment_amount=Decimal("1000.00"),
        status="active",
    )
    create_obligation(
        db_session,
        user_id=user_id,
        monthly_installment_amount=Decimal("750.50"),
        status="late",
    )
    create_obligation(
        db_session,
        user_id=user_id,
        monthly_installment_amount=Decimal("500.00"),
        status="completed",
    )
    create_obligation(
        db_session,
        user_id=user_id,
        monthly_installment_amount=Decimal("400.00"),
        start_date=add_months(current_month_start(), 1),
    )

    response = client.get(
        "/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["current_month_obligation_payments"] == "1750.50"
    assert data["current_month_projected_buffer"] == "4749.50"
    assert data["has_current_month_negative_buffer"] is False
    assert data["active_obligations_count"] == 3


def test_get_dashboard_summary_flags_negative_buffer(
    client: TestClient,
    db_session: Session,
) -> None:
    user_id, token = register_and_login(
        client,
        email="dashboard.negative@example.com",
        monthly_income="5000.00",
        fixed_expenses="2500.00",
    )
    create_obligation(
        db_session,
        user_id=user_id,
        monthly_installment_amount=Decimal("3000.00"),
    )

    response = client.get(
        "/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["current_month_projected_buffer"] == "-500.00"
    assert data["has_current_month_negative_buffer"] is True


def test_get_dashboard_summary_uses_authenticated_users_income_and_expenses(
    client: TestClient,
) -> None:
    _user_id, token = register_and_login(
        client,
        email="dashboard.profile@example.com",
        monthly_income="6000.00",
        fixed_expenses="6000.00",
    )

    response = client.get(
        "/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["monthly_income"] == "6000.00"
    assert data["fixed_expenses"] == "6000.00"
    assert data["current_month_projected_buffer"] == "0.00"


def test_get_dashboard_summary_rejects_client_supplied_inputs(client: TestClient) -> None:
    _user_id, token = register_and_login(client, email="dashboard.extra@example.com")

    response = client.get(
        "/dashboard/summary",
        params={
            "monthly_income": "99999.00",
            "fixed_expenses": "0.00",
            "user_id": 9999,
            "current_month": "2026-01-01",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Dashboard summary does not accept query parameters"
