"""Boundary and transaction regressions against disposable application-policy SQLite."""
from decimal import Decimal
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.deps import get_db
from app.core.security import create_access_token
from app.db.database import Base, create_app_engine
from app.main import app
from app.models.obligation import Obligation
from app.models.user import User
from app.schemas.obligation import ObligationCreate, ObligationUpdate
from app.schemas.validation import MAX_TERM_MONTHS

PAYLOAD = dict(provider="  تمويل Finance  ", item_name=" هاتف Phone ", category=" أجهزة ",
               total_amount="100.00", monthly_installment_amount="20.00",
               start_date="2026-01-31", term_months=5, due_day_of_month=31)


@pytest.fixture
def api():
    engine = create_app_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        owner = User(name="Owner", email="owner@example.com", password_hash="unused")
        other = User(name="Other", email="other@example.com", password_hash="unused")
        session.add_all([owner, other]); session.commit()
        ids = owner.id, other.id
        def override():
            yield session
        app.dependency_overrides[get_db] = override
        headers = {"Authorization": "Bearer " + create_access_token(subject=str(ids[0]))}
        with TestClient(app) as client:
            yield client, session, headers, ids
        app.dependency_overrides.clear()
    engine.dispose()


def post(api, **changes):
    client, _, headers, _ = api
    return client.post("/obligations", headers=headers, json=PAYLOAD | changes)


@pytest.mark.parametrize("field", list(ObligationCreate.model_fields))
def test_explicit_null_rejected_on_create_and_update(api, field):
    assert post(api, **{field: None}).status_code == 422
    created = post(api).json()
    client, _, headers, _ = api
    response = client.put(f"/obligations/{created['id']}", headers=headers, json={field: None})
    assert response.status_code == 422
    assert client.get(f"/obligations/{created['id']}", headers=headers).json()[field] is not None


@pytest.mark.parametrize("value", [None, "-0.01", "10000000000", "1.001", "NaN", "Infinity", "-Infinity", "garbage", True, "1e100000"])
@pytest.mark.parametrize("target", ["total_amount", "monthly_installment_amount", "monthly_income", "fixed_expenses", "amount"])
def test_invalid_money_is_422(api, target, value):
    client, _, headers, _ = api
    if target in ("total_amount", "monthly_installment_amount"):
        response = post(api, **{target: value})
    elif target == "amount":
        response = client.post("/affordability", headers=headers,
                               json=dict(amount=value, start_date="2026-01-01", term_months=1))
    else:
        response = client.patch("/auth/me", headers=headers, json={target: value})
    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize("value", [0, "0.01", "9999999999.99", "1.2300", 123.45])
def test_valid_money_roundtrips_without_loss(api, value):
    response = post(api, total_amount=value)
    assert response.status_code == 201, response.text
    assert Decimal(response.json()["total_amount"]) == Decimal(str(value))


@pytest.mark.parametrize("duration,expected", [(1, 201), (1200, 201), (1201, 422), (10**100, 422), (0, 422), (-1, 422), (True, 422), (1.5, 422)])
def test_duration_boundaries(api, duration, expected):
    assert MAX_TERM_MONTHS == 1200
    assert post(api, term_months=duration).status_code == expected
    client, _, headers, _ = api
    response = client.post("/affordability", headers=headers,
                           json=dict(amount="1.00", start_date="2026-01-01", term_months=duration))
    assert response.status_code == (200 if expected == 201 else 422)
    if expected == 201:
        assert len(response.json()["monthly_results"]) == duration
    elif isinstance(duration, int) and duration > 1200:
        assert "1200" in response.text


@pytest.mark.parametrize("field", ["provider", "item_name", "category"])
@pytest.mark.parametrize("value", ["", " \t\n ", "x" * 161])
def test_empty_or_oversized_text_rejected(api, field, value):
    assert post(api, **{field: value}).status_code == 422
    with pytest.raises(ValidationError):
        ObligationUpdate(**{field: value})


def test_trimmed_unicode_and_no_price_installment_rule(api):
    response = post(api, total_amount="0", monthly_installment_amount="999.99")
    assert response.status_code == 201
    assert response.json()["provider"] == "تمويل Finance"
    assert response.json()["item_name"] == "هاتف Phone"
    assert response.json()["category"] == "أجهزة"


@pytest.mark.parametrize("start", ["2026-02-29", "2026-04-31", "0000-01-01", "10000-01-01", None])
def test_invalid_dates_are_422(api, start):
    assert post(api, start_date=start).status_code == 422
    client, _, headers, _ = api
    assert client.post("/affordability", headers=headers,
                       json=dict(amount="1", start_date=start, term_months=1)).status_code == 422


def test_calendar_boundaries_and_merged_update_are_validated_before_mutation(api):
    assert post(api, start_date="9999-12-31", term_months=1).status_code == 201
    assert post(api, start_date="9999-12-01", term_months=2).status_code == 422
    original = post(api, start_date="9999-11-01", term_months=2).json()
    client, _, headers, _ = api
    url = f"/obligations/{original['id']}"
    assert client.put(url, headers=headers, json={"start_date": "9999-12-01"}).status_code == 422
    assert client.get(url, headers=headers).json() == original
    assert client.put(url, headers=headers, json={"term_months": 1, "start_date": "9999-12-01"}).status_code == 200
    assert client.put(url, headers=headers, json={}).status_code == 200
    assert client.post("/affordability", headers=headers,
                       json=dict(amount="1", start_date="9999-12-01", term_months=1)).status_code == 422
    assert client.post("/affordability", headers=headers,
                       json=dict(amount="1", start_date="9999-11-30", term_months=1)).status_code == 200


@pytest.mark.parametrize("start,months,expected", [("9999-12-31",1,200), ("9999-12-01",2,422), ("9999-01-01",60,422), ("0001-01-15",60,200), ("2026-01-01",0,422), ("2026-01-01",61,422), ("2026-01-01",10**100,422), ("2026-02-30",1,422)])
def test_forecast_extreme_dates(api, start, months, expected):
    client, _, headers, _ = api
    assert client.get("/forecast", headers=headers, params={"start_month":start,"months":months}).status_code == expected


def test_registration_name_and_optional_financial_profile(api):
    client, _, headers, _ = api
    body = dict(name=" \t ", email="new@example.com", password="valid password")
    assert client.post("/auth/register", json=body).status_code == 422
    body["name"] = "  اسم Name  "
    response = client.post("/auth/register", json=body)
    assert response.status_code == 201
    assert response.json()["name"] == "اسم Name"
    assert Decimal(response.json()["monthly_income"]) == 0
    assert client.post("/auth/login", json={"email":body["email"],"password":body["password"]}).status_code == 200
    assert client.patch("/auth/me", headers=headers, json={}).status_code == 200
    assert client.patch("/auth/me", headers=headers, json={"currency":None}).status_code == 422
    assert client.patch("/auth/me", headers=headers, json={"currency":"  "}).status_code == 422
    assert client.get("/dashboard/summary", headers=headers).status_code == 200
    assert client.post("/affordability", headers=headers, json={"amount":"0","start_date":"2026-01-01","term_months":1}).status_code == 200


@pytest.mark.parametrize("operation", ["profile", "create", "update", "delete"])
@pytest.mark.parametrize("failure", [IntegrityError, OperationalError])
def test_failed_mutation_rolls_back_and_session_recovers(api, monkeypatch, operation, failure):
    client, session, headers, _ = api
    existing = post(api).json()
    url = f"/obligations/{existing['id']}"
    def fail_once():
        # A real failed flush puts SQLAlchemy into its pending-rollback state.
        if failure is IntegrityError:
            session.add(Obligation(**ObligationCreate(**PAYLOAD).model_dump(), user_id=999999))
            session.flush()
        raise failure("PRIVATE SQL", {}, Exception("PRIVATE DRIVER DETAIL"))
    with monkeypatch.context() as m:
        m.setattr(session, "commit", fail_once)
        if operation == "profile":
            response = client.patch("/auth/me", headers=headers, json={"monthly_income":"500"})
        elif operation == "create":
            response = post(api)
        elif operation == "update":
            response = client.put(url, headers=headers, json={"provider":"changed"})
        else:
            response = client.delete(url, headers=headers)
    assert response.status_code == (409 if failure is IntegrityError else 500)
    assert "PRIVATE" not in response.text and "sqlalchemy" not in response.text
    assert client.get(url, headers=headers).json() == existing
    assert Decimal(client.get("/auth/me", headers=headers).json()["monthly_income"]) == 0
    assert post(api).status_code == 201


def test_fk_policy_every_connection_and_cascade(tmp_path):
    engine = create_app_engine("sqlite:///" + str(tmp_path / "integrity.db"))
    Base.metadata.create_all(engine)
    for _ in range(2):
        with engine.connect() as connection:
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        engine.dispose()  # Prove policy applies on a replacement connection too.
    with Session(engine) as session:
        session.add(Obligation(**ObligationCreate(**PAYLOAD).model_dump(), user_id=999))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        user = User(name="owner",email="cascade@example.com",password_hash="unused")
        session.add(user); session.commit()
        session.add(Obligation(**ObligationCreate(**PAYLOAD).model_dump(), user_id=user.id)); session.commit()
        session.execute(delete(User).where(User.id == user.id)); session.commit()
        assert session.query(Obligation).count() == 0
    engine.dispose()


def test_dependency_rolls_back_and_closes_on_failure(monkeypatch):
    session = Mock()
    monkeypatch.setattr(deps, "SessionLocal", lambda: session)
    dependency = deps.get_db()
    assert next(dependency) is session
    with pytest.raises(RuntimeError):
        dependency.throw(RuntimeError("failed request"))
    session.rollback.assert_called_once()
    session.close.assert_called_once()


def test_ownership_and_parameterized_text(api):
    client, session, headers, ids = api
    original = post(api, provider="'); DROP TABLE users; --").json()
    outsider = {"Authorization":"Bearer " + create_access_token(subject=str(ids[1]))}
    url = f"/obligations/{original['id']}"
    assert client.get(url,headers=outsider).status_code == 404
    assert client.put(url,headers=outsider,json={"provider":"stolen"}).status_code == 404
    assert client.delete(url,headers=outsider).status_code == 404
    assert client.get("/obligations",headers=outsider).json() == []
    assert client.get(url,headers=headers).json() == original
    assert session.query(User).count() == 2


@pytest.mark.parametrize("numeric", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("path,body", [
    ("/obligations", '{"provider":"p","item_name":"i","category":"c","total_amount":VALUE,"monthly_installment_amount":0,"start_date":"2026-01-01","term_months":1,"due_day_of_month":1}'),
    ("/affordability", '{"amount":VALUE,"start_date":"2026-01-01","term_months":1}'),
    ("/auth/me", '{"monthly_income":VALUE}'),
])
def test_nonstandard_nonfinite_json_returns_safe_422(api, numeric, path, body):
    client, _, headers, _ = api
    response = client.request("PATCH" if path == "/auth/me" else "POST", path,
                              headers=headers | {"Content-Type":"application/json"},
                              content=body.replace("VALUE", numeric))
    assert response.status_code == 422
    assert all(set(error) == {"type", "loc", "msg"} for error in response.json()["detail"])


@pytest.mark.parametrize("field,value", [
    ("total_amount", "1.001"), ("monthly_installment_amount", "10000000000"),
    ("term_months", 1201), ("term_months", 10**100),
    ("due_day_of_month", True), ("due_day_of_month", 32),
])
def test_invalid_partial_updates_leave_original_record(api, field, value):
    original = post(api).json()
    client, _, headers, _ = api
    url = f"/obligations/{original['id']}"
    assert client.put(url, headers=headers, json={field:value}).status_code == 422
    assert client.get(url, headers=headers).json() == original


def test_legacy_duration_is_readable_and_never_automatically_shortened(api):
    client, session, headers, ids = api
    record = Obligation(**(ObligationCreate(**PAYLOAD).model_dump() | {"term_months":1201}), user_id=ids[0])
    session.add(record); session.commit()
    url = f"/obligations/{record.id}"
    assert client.get(url,headers=headers).json()["term_months"] == 1201
    assert client.put(url,headers=headers,json={"provider":"new name"}).status_code == 422
    session.refresh(record)
    assert record.term_months == 1201 and record.provider == "تمويل Finance"


def test_valid_leap_date_and_due_day_31_remain_supported(api):
    assert post(api, start_date="2028-02-29", due_day_of_month=31).status_code == 201
