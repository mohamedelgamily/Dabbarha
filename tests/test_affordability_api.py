from collections.abc import Generator
from datetime import date
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
    name: str = "Affordability User",
    email: str = "affordability@example.com",
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


def test_authenticated_successful_request(client: TestClient, db_session: Session) -> None:
    user_id, token = register_and_login(
        client,
        monthly_income="10000.00",
        fixed_expenses="2000.00",
    )
    create_obligation(
        db_session,
        user_id=user_id,
        monthly_installment_amount=Decimal("1000.00"),
        start_date=date(2026, 1, 1),
        term_months=1,
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "1500.00",
            "start_date": "2026-01-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "Comfortable"
    assert data["worst_projected_buffer"] == "5500.00"
    assert data["worst_buffer_percentage"] == "55.00"
    assert data["worst_month"] == "2026-01-01"
    assert data["explanation"] == "This commitment appears affordable."
    assert len(data["monthly_results"]) == 1
    assert data["monthly_results"][0]["proposed_commitment_amount"] == "1500.00"
    assert data["monthly_results"][0]["existing_obligation_payments"] == "1000.00"


def test_unauthenticated_request_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/affordability",
        json={
            "amount": "1000.00",
            "start_date": "2026-01-01",
            "term_months": 1,
        },
    )
    assert response.status_code == 401


def test_user_isolation(client: TestClient, db_session: Session) -> None:
    user_a_id, token_a = register_and_login(
        client,
        name="User A",
        email="user.a@example.com",
        monthly_income="5000.00",
        fixed_expenses="2000.00",
    )
    _user_b_id, _token_b = register_and_login(
        client,
        name="User B",
        email="user.b@example.com",
        monthly_income="5000.00",
        fixed_expenses="2000.00",
    )
    create_obligation(
        db_session,
        user_id=user_a_id,
        monthly_installment_amount=Decimal("2000.00"),
        start_date=date(2026, 1, 1),
        term_months=3,
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "1000.00",
            "start_date": "2026-01-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["monthly_results"][0]["existing_obligation_payments"] == "2000.00"


def test_uses_authenticated_users_financial_profile(client: TestClient, db_session: Session) -> None:
    user_id, token = register_and_login(
        client,
        monthly_income="8000.00",
        fixed_expenses="3000.00",
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "1000.00",
            "start_date": "2026-01-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["monthly_results"][0]["income"] == "8000.00"
    assert data["monthly_results"][0]["fixed_expenses"] == "3000.00"


def test_client_cannot_override_financial_profile(client: TestClient, db_session: Session) -> None:
    user_id, token = register_and_login(
        client,
        monthly_income="10000.00",
        fixed_expenses="2000.00",
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "1000.00",
            "start_date": "2026-01-01",
            "term_months": 1,
            "monthly_income": "50000.00",
            "fixed_expenses": "0.00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_client_cannot_supply_user_id(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(client)

    response = client.post(
        "/affordability",
        json={
            "amount": "1000.00",
            "start_date": "2026-01-01",
            "term_months": 1,
            "user_id": 999,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_no_obligations(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(
        client,
        monthly_income="10000.00",
        fixed_expenses="2000.00",
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "1000.00",
            "start_date": "2026-01-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["monthly_results"][0]["existing_obligation_payments"] == "0.00"


def test_existing_obligations_included(client: TestClient, db_session: Session) -> None:
    user_id, token = register_and_login(
        client,
        monthly_income="10000.00",
        fixed_expenses="2000.00",
    )
    create_obligation(
        db_session,
        user_id=user_id,
        monthly_installment_amount=Decimal("1500.00"),
        start_date=date(2026, 1, 1),
        term_months=2,
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "1000.00",
            "start_date": "2026-01-01",
            "term_months": 2,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["monthly_results"][0]["existing_obligation_payments"] == "1500.00"
    assert data["monthly_results"][1]["existing_obligation_payments"] == "1500.00"


def test_comfortable_classification(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(
        client,
        monthly_income="10000.00",
        fixed_expenses="2000.00",
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "1000.00",
            "start_date": "2026-01-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "Comfortable"


def test_manageable_classification(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(
        client,
        monthly_income="5000.00",
        fixed_expenses="2500.00",
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "1000.00",
            "start_date": "2026-01-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "Manageable"


def test_risky_classification(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(
        client,
        monthly_income="5000.00",
        fixed_expenses="4000.00",
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "500.00",
            "start_date": "2026-01-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "Risky"


def test_not_affordable_classification(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(
        client,
        monthly_income="5000.00",
        fixed_expenses="4000.00",
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "2000.00",
            "start_date": "2026-01-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "Not Affordable"


def test_exactly_zero_buffer_is_risky(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(
        client,
        monthly_income="5000.00",
        fixed_expenses="4000.00",
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "1000.00",
            "start_date": "2026-01-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "Risky"
    assert data["worst_projected_buffer"] == "0.00"
    assert data["worst_buffer_percentage"] == "0"


def test_multi_month_commitment(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(
        client,
        monthly_income="10000.00",
        fixed_expenses="3000.00",
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "2000.00",
            "start_date": "2026-01-01",
            "term_months": 3,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["monthly_results"]) == 3
    for month_result in data["monthly_results"]:
        assert month_result["proposed_commitment_amount"] == "2000.00"


def test_entire_commitment_period_is_evaluated(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(
        client,
        monthly_income="5000.00",
        fixed_expenses="2000.00",
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "2500.00",
            "start_date": "2026-02-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["worst_month"] == "2026-02-01"
    assert data["monthly_results"][0]["month"] == "2026-02-01"


def test_response_contains_worst_month_and_monthly_results(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(
        client,
        monthly_income="5000.00",
        fixed_expenses="2000.00",
    )

    response = client.post(
        "/affordability",
        json={
            "amount": "2500.00",
            "start_date": "2026-02-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "worst_month" in data
    assert "monthly_results" in data
    assert len(data["monthly_results"]) == 1


def test_invalid_amount_is_rejected(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(client)

    response = client.post(
        "/affordability",
        json={
            "amount": "-1.00",
            "start_date": "2026-01-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_invalid_term_months_is_rejected(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(client)

    response = client.post(
        "/affordability",
        json={
            "amount": "1000.00",
            "start_date": "2026-01-01",
            "term_months": 0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_unexpected_query_parameters_are_rejected(client: TestClient, db_session: Session) -> None:
    _user_id, token = register_and_login(client)

    response = client.post(
        "/affordability?extra=param",
        json={
            "amount": "1000.00",
            "start_date": "2026-01-01",
            "term_months": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
