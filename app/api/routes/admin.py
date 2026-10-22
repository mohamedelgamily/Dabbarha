"""Default-off administrator authentication and read-only operational APIs."""
import time
from uuid import uuid4

import jwt
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_current_user, get_db, resolve_current_user
from app.api.routes.sessions import session_identity
from app.core.config import JWT_ALGORITHM, JWT_SECRET_KEY
from app.core.api_security import source_ip
from app.models.auth_session import AuthSession
from app.models.notifications import Notification, NotificationDelivery, PushDevice
from app.models.user import User
from pydantic.networks import EmailStr
from app.schemas.admin import AdminStepUpRequest, AdminStepUpResponse
from app.services.admin_operations import (
    apply_read_timeout, commit_admin_audit, overview as operational_overview, safe_error_category, system_health,
)
from app.services.admin_security import (
    decrypt_totp_secret, matching_totp_step, require_admin_api, require_admin_stepup, write_audit,
)

admin_bearer = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _audit_action(request: Request) -> str:
    path = request.url.path.rstrip("/")
    if "/support-grants/" in path and "/users/" in path:
        return "support_financial_access"
    if path.endswith("/support-grants"):
        return "support_grant_request"
    if "/support-grants/" in path and path.endswith("/approve"):
        return "support_grant_approval"
    if "/support-grants/" in path and path.endswith("/revoke"):
        return "support_grant_revocation"
    if "/support-grants/" in path:
        return "support_grant_inspection"
    if path.endswith("/ops/overview"):
        return "admin_overview"
    if path.endswith("/ops/health"):
        return "admin_health_check"
    if path.endswith("/auth/me"):
        return "admin_identity"
    if path.endswith("/users/lookup"):
        return "admin_user_lookup"
    if path.endswith("/sessions") and "/users/" in path:
        return "admin_user_sessions"
    if path.endswith("/deliveries"):
        return "admin_notification_inspection"
    return "admin_operational_access"


def admin_api_gate(request: Request, db=Depends(get_db)) -> None:
    if request.app.state.admin_settings.enabled:
        return
    try:
        commit_admin_audit(db, request, _audit_action(request), "failure")
    except HTTPException:
        # Disabled routes stay indistinguishable even before the audit migration
        # is installed or while the audit store itself is unavailable.
        db.rollback()
    raise HTTPException(404, "Not found")


router = APIRouter(dependencies=[Depends(admin_api_gate)])


def require_operational_admin(request: Request, authorization: str | None = Header(default=None),
                              token: str | None = Depends(admin_bearer), db=Depends(get_db)) -> User:
    """Use the normal v2 session resolver, then require the Phase 2f.1 MFA token.

    Failed attempts are also audited where storage is available. The IP limiter
    runs in ASGI middleware before this dependency; authenticated admin traffic
    additionally consumes the per-admin Redis quota in resolve_current_user.
    """
    action = _audit_action(request)
    if token is None and authorization:
        scheme, _, value = authorization.partition(" ")
        token = value if scheme.lower() == "bearer" and value else None
    actor = None
    try:
        if not token:
            raise HTTPException(401, "Could not validate credentials.",
                                headers={"WWW-Authenticate": "Bearer"})
        actor = resolve_current_user(request, token, db)
        require_admin_stepup(request, actor)
    except HTTPException:
        try:
            commit_admin_audit(db, request, action, "failure", actor_id=actor.id if actor else None)
        except HTTPException:
            raise
        raise
    commit_admin_audit(db, request, action, "success", actor_id=actor.id)
    return actor


def _target_audit(db, request: Request, actor: User, user_id: int | None, outcome: str = "success") -> None:
    commit_admin_audit(db, request, "admin_user_inspection", outcome,
                       actor_id=actor.id, target_id=user_id)


def _epoch_iso(value: int | None) -> str | None:
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


def _raise_admin_storage_unavailable(db):
    db.rollback()
    raise HTTPException(503, "Operational data is temporarily unavailable.",
                        headers={"Retry-After": "1"}) from None


def _delivery_record(delivery: NotificationDelivery, notification: Notification,
                     device: PushDevice) -> dict:
    return {
        "delivery_id": delivery.id,
        "notification_id": notification.id,
        "user_id": notification.user_id,
        "notification_type": notification.notification_type,
        "state": delivery.delivery_state,
        "platform": device.platform,
        "attempt_count": delivery.attempt_count,
        "receipt_attempt_count": delivery.receipt_attempt_count,
        "error_category": safe_error_category(delivery.error_code),
        "created_at": delivery.created_at.isoformat(),
        "last_attempt_at": delivery.last_attempt_at.isoformat() if delivery.last_attempt_at else None,
        "updated_at": delivery.updated_at.isoformat(),
    }


@router.post("/auth/step-up", response_model=AdminStepUpResponse)
def step_up(body: AdminStepUpRequest, request: Request,
            identity=Depends(session_identity), db=Depends(get_db)):
    user, session_id = identity
    runtime = request.app.state.security
    source = source_ip(request.scope)
    reservation = runtime.login_reserve(user.email, source)
    db.rollback()
    now = int(time.time())
    try:
        if db.get_bind().dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        elif db.get_bind().dialect.name == "postgresql":
            db.execute(text("SELECT set_config('lock_timeout', '3s', true)"))
        row = db.scalar(select(User).where(User.id == user.id).with_for_update())
        valid_step = None
        if row is not None and row.admin_role in {"admin", "superadmin"}:
            settings = request.app.state.admin_settings
            if (row.admin_totp_nonce is None or row.admin_totp_ciphertext is None
                    or row.admin_totp_key_id != settings.totp_key_id):
                write_audit(db, runtime.settings.hmac_key, "admin_totp_factor_unavailable", "failure",
                            actor_id=user.id, source=source)
                db.commit()
                raise HTTPException(503, "Administrator verification is temporarily unavailable.",
                                    headers={"Retry-After": "1"})
            try:
                secret = decrypt_totp_secret(row.admin_totp_nonce, row.admin_totp_ciphertext,
                                             row.id, settings, row.admin_totp_key_id)
            except Exception:
                write_audit(db, runtime.settings.hmac_key, "admin_totp_factor_unavailable", "failure",
                            actor_id=user.id, source=source)
                db.commit()
                raise HTTPException(503, "Administrator verification is temporarily unavailable.",
                                    headers={"Retry-After": "1"}) from None
            valid_step = matching_totp_step(secret, body.code, now, row.admin_totp_last_step)
        if valid_step is None:
            write_audit(db, runtime.settings.hmac_key, "admin_totp_step_up", "failure",
                        actor_id=user.id, source=source)
            db.commit()  # Persist failed attempts without retaining client input or secrets.
            raise HTTPException(401, "Administrator verification failed.", headers={"WWW-Authenticate": "Bearer"})
        row.admin_totp_last_step = valid_step
        write_audit(db, runtime.settings.hmac_key, "admin_totp_step_up", "success",
                    actor_id=row.id, source=source)
        db.commit()
        runtime.limiter.release(reservation)
        expires = now + request.app.state.admin_settings.stepup_minutes * 60
        token = jwt.encode({
            "sub": str(row.id), "sid": session_id, "jti": str(uuid4()), "iat": now,
            "exp": expires, "token_use": "admin_stepup", "ver": 2,
            "admin_role": row.admin_role, "admin_mfa_at": now,
        }, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return AdminStepUpResponse(access_token=token, expires_in=expires - now,
                                   admin_role=row.admin_role)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(503, "Administrator verification is temporarily unavailable.",
                            headers={"Retry-After": "1"}) from None


def require_stepup(request: Request, user: User = Depends(get_current_user)):
    return require_admin_stepup(request, user)


@router.get("/auth/me")
def admin_identity(request: Request, user: User = Depends(get_current_user),
                   stepup=Depends(require_stepup), db=Depends(get_db)):
    # A deliberately minimal probe for clients; no email, password or factor material.
    commit_admin_audit(db, request, "admin_identity", "success", actor_id=user.id)
    return {"admin_role": user.admin_role, "step_up_expires_at": stepup["exp"]}


@router.get("/ops/overview")
def operations_overview(
    request: Request,
    window_days: int = Query(default=7, ge=1, le=30),
    actor: User = Depends(require_operational_admin),
    db=Depends(get_db),
):
    try:
        apply_read_timeout(db)
        return operational_overview(db, datetime.now(timezone.utc), window_days,
                                   request.app.state.notification_settings)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Operational metrics are temporarily unavailable.",
                            headers={"Retry-After": "1"}) from None


@router.get("/ops/health")
def operations_health(request: Request, actor: User = Depends(require_operational_admin), db=Depends(get_db)):
    try:
        return system_health(db, request, datetime.now(timezone.utc))
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "System health is temporarily unavailable.",
                            headers={"Retry-After": "1"}) from None


@router.get("/users/lookup")
def lookup_user(
    request: Request,
    user_id: int | None = Query(default=None, ge=1),
    email: EmailStr | None = Query(default=None),
    actor: User = Depends(require_operational_admin),
    db=Depends(get_db),
):
    if (user_id is None) == (email is None):
        raise HTTPException(422, "Provide exactly one exact user_id or email.")
    if email is not None and any(marker in email for marker in ("*", "?", "%")):
        raise HTTPException(422, "Provide one exact email address.")
    normalized = email.strip().lower() if email is not None else None
    try:
        apply_read_timeout(db)
        user = db.get(User, user_id) if user_id is not None else db.scalar(select(User).where(User.email == normalized))
    except SQLAlchemyError:
        _raise_admin_storage_unavailable(db)
    _target_audit(db, request, actor, user.id if user else None, "success" if user else "failure")
    if user is None:
        raise HTTPException(404, "Account not found.")
    return {
        "account_id": user.id,
        "display_name": user.name,
        "email": user.email,
        "registered_at": user.created_at.isoformat(),
        "admin_role": user.admin_role,
        "account_state": "present",
        "account_state_note": "Accounts have no suspension status in this backend.",
    }


@router.get("/users/{user_id}/sessions")
def inspect_user_sessions(
    request: Request,
    user_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    actor: User = Depends(require_operational_admin),
    db=Depends(get_db),
):
    try:
        apply_read_timeout(db)
        user = db.get(User, user_id)
    except SQLAlchemyError:
        _raise_admin_storage_unavailable(db)
    if user is None:
        _target_audit(db, request, actor, None, "failure")
        raise HTTPException(404, "Account not found.")
    _target_audit(db, request, actor, user.id)
    try:
        apply_read_timeout(db)
        rows = db.scalars(select(AuthSession).where(AuthSession.user_id == user_id)
                          .order_by(AuthSession.created_at.desc(), AuthSession.id).offset(offset).limit(limit + 1)).all()
        page = rows[:limit]
        now = int(datetime.now(timezone.utc).timestamp())
        result = []
        for row in page:
            devices = db.scalars(select(PushDevice).where(PushDevice.user_id == user_id,
                                                            PushDevice.session_id == row.id)
                                 .order_by(PushDevice.id)).all()
            active = (row.revoked_at is None and row.idle_expires_at > now and row.absolute_expires_at > now)
            result.append({
                "session_id": row.id, "device_label": row.device_label,
                "created_at": _epoch_iso(row.created_at), "last_refreshed_at": _epoch_iso(row.last_refreshed_at),
                "idle_expires_at": _epoch_iso(row.idle_expires_at), "absolute_expires_at": _epoch_iso(row.absolute_expires_at),
                "revoked_at": _epoch_iso(row.revoked_at), "active": active,
                "devices": [{"device_id": d.id, "platform": d.platform, "active": d.active,
                             "last_registered_at": d.last_registered_at.isoformat()} for d in devices],
            })
    except SQLAlchemyError:
        _raise_admin_storage_unavailable(db)
    return {"items": result, "offset": offset, "limit": limit,
            "next_offset": offset + limit if len(rows) > limit else None}


@router.get("/users/{user_id}/deliveries")
def inspect_user_deliveries(
    request: Request,
    user_id: int,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    state: str | None = Query(default=None, pattern=r"^(queued|sending|accepted|platform_accepted|failed|cancelled)$"),
    actor: User = Depends(require_operational_admin),
    db=Depends(get_db),
):
    try:
        apply_read_timeout(db)
        user = db.get(User, user_id)
    except SQLAlchemyError:
        _raise_admin_storage_unavailable(db)
    if user is None:
        _target_audit(db, request, actor, None, "failure")
        raise HTTPException(404, "Account not found.")
    _target_audit(db, request, actor, user.id)
    try:
        apply_read_timeout(db)
        statement = select(NotificationDelivery, Notification, PushDevice).join(
            Notification, Notification.id == NotificationDelivery.notification_id).join(
            PushDevice, PushDevice.id == NotificationDelivery.device_id).where(
                Notification.user_id == user_id, NotificationDelivery.id > after_id)
        if state:
            statement = statement.where(NotificationDelivery.delivery_state == state)
        rows = db.execute(statement.order_by(NotificationDelivery.id).limit(limit + 1)).all()
    except SQLAlchemyError:
        _raise_admin_storage_unavailable(db)
    items = [_delivery_record(delivery, notification, device) for delivery, notification, device in rows[:limit]]
    return {"items": items, "after_id": after_id, "limit": limit,
            "next_cursor": items[-1]["delivery_id"] if len(rows) > limit else None}


@router.get("/notifications/deliveries")
def inspect_notification_deliveries(
    state: str | None = Query(default=None, pattern=r"^(queued|sending|accepted|platform_accepted|failed|cancelled)$"),
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    actor: User = Depends(require_operational_admin),
    db=Depends(get_db),
):
    try:
        apply_read_timeout(db)
        statement = select(NotificationDelivery, Notification, PushDevice).join(
            Notification, Notification.id == NotificationDelivery.notification_id).join(
            PushDevice, PushDevice.id == NotificationDelivery.device_id).where(NotificationDelivery.id > after_id)
        if state:
            statement = statement.where(NotificationDelivery.delivery_state == state)
        rows = db.execute(statement.order_by(NotificationDelivery.id).limit(limit + 1)).all()
    except SQLAlchemyError:
        _raise_admin_storage_unavailable(db)
    items = [_delivery_record(delivery, notification, device) for delivery, notification, device in rows[:limit]]
    return {"items": items, "after_id": after_id, "limit": limit,
            "next_cursor": items[-1]["delivery_id"] if len(rows) > limit else None}


# Kept in a separate module so the support-access boundary stays reviewable.
from app.api.routes.admin_support import router as support_router
router.include_router(support_router)
