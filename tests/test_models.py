from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models import Obligation, User


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as test_session:
        yield test_session

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def make_user(**overrides) -> User:
    values = {
        "name": "Nour Hassan",
        "email": "nour@example.com",
        "password_hash": "hashed-password-placeholder",
        "monthly_income": Decimal("25000.00"),
        "fixed_expenses": Decimal("7500.50"),
    }
    values.update(overrides)
    return User(**values)


def make_obligation(user: User | None = None, **overrides) -> Obligation:
    values = {
        "provider": "ValU",
        "item_name": "Laptop installment",
        "category": "electronics",
        "total_amount": Decimal("36000.00"),
        "monthly_installment_amount": Decimal("3000.00"),
        "start_date": date(2026, 8, 1),
        "term_months": 12,
        "due_day_of_month": 15,
    }
    values.update(overrides)

    if user is not None:
        values["user"] = user

    return Obligation(**values)


def assert_integrity_error(session: Session, instance: object) -> None:
    session.add(instance)

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_valid_user_can_be_created_and_persisted(session: Session) -> None:
    user = make_user()

    session.add(user)
    session.commit()
    session.refresh(user)

    assert user.id is not None
    assert user.currency == "EGP"
    assert user.created_at is not None
    assert user.monthly_income == Decimal("25000.00")
    assert user.fixed_expenses == Decimal("7500.50")


def test_valid_obligation_can_be_created_with_user_relationship(session: Session) -> None:
    user = make_user()
    obligation = make_obligation(user=user)

    session.add(user)
    session.commit()
    session.refresh(user)
    session.refresh(obligation)

    assert obligation.id is not None
    assert obligation.user_id == user.id
    assert obligation in user.obligations
    assert obligation.user is user
    assert obligation.status == "active"
    assert obligation.source == "manual_entry"
    assert obligation.created_at is not None
    assert obligation.updated_at is not None


@pytest.mark.parametrize(
    "field,value",
    [
        ("monthly_income", Decimal("-0.01")),
        ("fixed_expenses", Decimal("-0.01")),
    ],
)
def test_user_money_constraints_reject_negative_values(
    session: Session,
    field: str,
    value: Decimal,
) -> None:
    assert_integrity_error(session, make_user(**{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("total_amount", Decimal("-0.01")),
        ("monthly_installment_amount", Decimal("-0.01")),
        ("term_months", 0),
        ("due_day_of_month", 0),
        ("due_day_of_month", 32),
        ("status", "paused"),
        ("source", "spreadsheet_import"),
    ],
)
def test_obligation_constraints_reject_invalid_values(
    session: Session,
    field: str,
    value: object,
) -> None:
    user = make_user(email=f"{field}-{value}@example.com")
    session.add(user)
    session.commit()

    assert_integrity_error(session, make_obligation(user=user, **{field: value}))


def test_obligation_cannot_reference_nonexistent_user(session: Session) -> None:
    obligation = make_obligation(user_id=999)

    assert_integrity_error(session, obligation)


def test_user_email_must_be_unique(session: Session) -> None:
    first_user = make_user(email="duplicate@example.com")
    second_user = make_user(
        name="Mariam Ali",
        email="duplicate@example.com",
    )

    session.add(first_user)
    session.commit()

    assert_integrity_error(session, second_user)
