"""Cross-endpoint mobile journey using only a disposable SQLite database."""
from datetime import date
import secrets

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.notification_settings import NotificationSettings
from app.core.session_settings import SessionSettings
from app.db.database import Base, create_app_engine
from app.main import app
from app.models.auth_session import AuthSession
from app.models.notifications import Notification, PaymentOccurrence, PushDevice
from app.models.obligation import Obligation, ObligationInstallment
from app.models.user import User
from app.services.sessions import SessionService


def test_mobile_release_journey_is_consistent_and_deletion_is_final(tmp_path, monkeypatch):
    engine = create_app_engine(f"sqlite:///{tmp_path / 'journey.db'}")
    Base.metadata.create_all(engine)
    session_settings = SessionSettings(enabled=True, receipt_key=secrets.token_bytes(32))
    monkeypatch.setattr(app.state, "sessions", SessionService(session_settings))
    monkeypatch.setattr(app.state, "notification_settings", NotificationSettings(
        enabled=True, token_key=secrets.token_bytes(32)))

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            registration = client.post("/auth/register", json={
                "name": "Nour Hassan", "email": "journey@example.com", "password": "StrongPassphrase8",
            })
            assert registration.status_code == 201, registration.text
            login = client.post("/auth/sessions", json={
                "email": "journey@example.com", "password": "StrongPassphrase8", "device_label": "iPhone",
            })
            assert login.status_code == 200, login.text
            pair = login.json()
            headers = {"Authorization": f"Bearer {pair['access_token']}"}

            profile = client.patch("/auth/me", headers=headers, json={
                "monthly_income": "6000.00", "fixed_expenses": "1000.00", "currency": "EGP",
            })
            assert profile.status_code == 200, profile.text
            today = date.today()
            plan_response = client.post("/obligations/installment-plans", headers=headers, json={
                "provider": "Example Provider", "item_name": "Laptop", "category": "Electronics",
                "purchase_price": "300.00", "payment_method": "manual", "interest_method": "none",
                "monthly_installment_amount": "100.00", "down_payment_amount": "0.00",
                "start_date": today.isoformat(), "term_months": 3, "due_day_of_month": today.day,
            })
            assert plan_response.status_code == 201, plan_response.text
            obligation_id = plan_response.json()["id"]
            schedule = client.get(f"/obligations/{obligation_id}/installments", headers=headers)
            assert schedule.status_code == 200 and len(schedule.json()["installments"]) == 3

            dashboard = client.get("/dashboard/summary", headers=headers)
            assert dashboard.status_code == 200
            assert dashboard.json()["current_month_installment_payments"] == "100.00"
            forecast = client.get(f"/forecast?start_month={today.replace(day=1).isoformat()}&months=3", headers=headers)
            assert forecast.status_code == 200 and forecast.json()["rows"][0]["installment_payments"] == "100.00"
            affordability_body = {
                "purchase_price": "600.00", "payment_method": "automatic", "interest_method": "none",
                "start_date": today.isoformat(), "term_months": 3, "due_day_of_month": today.day,
            }
            affordability = client.post("/affordability", headers=headers, json=affordability_body)
            assert affordability.status_code == 200, affordability.text
            assert affordability.json()["monthly_results"][0]["existing_obligation_payments"] == "100.00"

            occurrence_response = client.get(
                f"/obligations/{obligation_id}/payment-occurrences?start_date={today.isoformat()}&months=1",
                headers=headers)
            assert occurrence_response.status_code == 200, occurrence_response.text
            occurrence = next(row for row in occurrence_response.json()["rows"] if row["payment_kind"] == "regular")
            preferences = client.put("/notifications/preferences", headers=headers, json={
                "reminders_enabled": True, "reminder_offsets": [7, 3, 1, 0], "reminder_time": "09:00",
                "timezone": "Africa/Cairo", "quiet_start": None, "quiet_end": None, "language": "ar",
                "privacy_mode": "private", "overdue_enabled": False,
                "categories": ["upcoming", "due_today", "payment_completed"],
            })
            assert preferences.status_code == 200, preferences.text
            device = client.post("/notifications/devices", headers=headers, json={
                "token": "ExpoPushToken[0123456789abcdef0123456789]", "platform": "ios",
            })
            assert device.status_code == 201, device.text
            assert "token" not in device.json()
            assert client.get("/notifications/devices", headers=headers).status_code == 200

            marked = client.post(
                f"/obligations/{obligation_id}/payment-occurrences/{occurrence['id']}/mark-paid", headers=headers)
            assert marked.status_code == 200 and marked.json()["state"] == "paid"
            dashboard_after = client.get("/dashboard/summary", headers=headers).json()
            assert dashboard_after["current_month_installment_payments"] == "0.00"
            forecast_after = client.get(
                f"/forecast?start_month={today.replace(day=1).isoformat()}&months=3", headers=headers).json()
            assert forecast_after["rows"][0]["installment_payments"] == "0.00"
            affordability_after = client.post("/affordability", headers=headers, json=affordability_body).json()
            assert affordability_after["monthly_results"][0]["existing_obligation_payments"] == "0.00"
            notifications = client.get("/notifications?limit=20", headers=headers)
            assert notifications.status_code == 200
            assert any(item["notification_type"] == "payment_completed" for item in notifications.json()["items"])

            retry_key = secrets.token_urlsafe(32)
            refreshed = client.post("/auth/refresh", json={
                "refresh_token": pair["refresh_token"], "retry_key": retry_key,
            })
            assert refreshed.status_code == 200, refreshed.text
            current_pair = refreshed.json()
            current_headers = {"Authorization": f"Bearer {current_pair['access_token']}"}
            assert client.get("/auth/me", headers=current_headers).status_code == 200
            logout = client.post("/auth/logout", json={"refresh_token": current_pair["refresh_token"]})
            assert logout.status_code == 204
            assert client.get("/auth/me", headers=current_headers).status_code == 401

            reauthenticated = client.post("/auth/sessions", json={
                "email": "journey@example.com", "password": "StrongPassphrase8", "device_label": "iPhone",
            })
            assert reauthenticated.status_code == 200, reauthenticated.text
            deleted = client.request("DELETE", "/auth/account",
                headers={"Authorization": f"Bearer {reauthenticated.json()['access_token']}"},
                json={"password": "StrongPassphrase8", "confirm_permanent_deletion": True})
            assert deleted.status_code == 204, deleted.text
            assert client.get("/auth/me", headers={
                "Authorization": f"Bearer {reauthenticated.json()['access_token']}"}).status_code == 401
            with Session(engine) as db:
                assert db.scalar(select(User.id).where(User.email == "journey@example.com")) is None
                assert db.scalar(select(Obligation.id)) is None
                assert db.scalar(select(ObligationInstallment.installment_number)) is None
                assert db.scalar(select(PaymentOccurrence.id)) is None
                assert db.scalar(select(PushDevice.id)) is None
                assert db.scalar(select(AuthSession.id)) is None
                assert db.scalar(select(Notification.id)) is None
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
