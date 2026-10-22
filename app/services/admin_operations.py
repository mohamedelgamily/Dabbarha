"""Read-only operational metrics with explicit bounds and redaction."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.notification_time import safe_now
from app.models.admin_operations import WorkerHeartbeat
from app.models.auth_session import AuthSession
from app.models.notifications import NotificationDelivery
from app.models.obligation import Obligation
from app.models.user import User

COMPONENT = "notification-worker"
ERROR_CATEGORY_MAP = {
    "device_token_unavailable": "device_token_unavailable",
    "notification_expired_or_no_longer_due": "notification_no_longer_eligible",
    "notification_no_longer_eligible": "notification_no_longer_eligible",
    "device_session_inactive": "device_session_inactive",
    "device_deactivated": "device_session_inactive",
    "delivery_outcome_unknown": "delivery_outcome_unknown",
    "temporary_provider_failure": "temporary_provider_failure",
    "provider_rejected": "provider_rejected",
    "receipt_unavailable": "receipt_unavailable",
    "receipt_expired": "receipt_expired",
    "provider_receipt_error": "provider_receipt_error",
    "DeviceNotRegistered": "push_device_invalid",
}


def safe_error_category(value: str | None) -> str | None:
    if value is None:
        return None
    return ERROR_CATEGORY_MAP.get(value, "other")


def write_admin_audit(db, request, action: str, outcome: str,
                      actor_id: int | None = None, target_id: int | None = None) -> None:
    from app.core.api_security import source_ip
    from app.services.admin_security import write_audit

    key = request.app.state.security.settings.hmac_key
    write_audit(db, key, action, outcome, actor_id=actor_id, target_id=target_id,
                source=source_ip(request.scope))


def commit_admin_audit(db, request, action: str, outcome: str,
                       actor_id: int | None = None, target_id: int | None = None) -> None:
    from fastapi import HTTPException

    write_admin_audit(db, request, action, outcome, actor_id, target_id)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Administrative audit storage is unavailable.",
                            headers={"Retry-After": "1"}) from None


def _count(db, statement) -> int:
    return int(db.scalar(statement) or 0)


def apply_read_timeout(db) -> None:
    """Bound PostgreSQL read work; the Redis adapter has its own socket timeout."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL statement_timeout = '3000ms'"))


def _worker_state(db, notification_settings, now: datetime) -> dict:
    if not notification_settings.enabled:
        return {"state": "disabled", "last_seen_at": None, "last_success_at": None,
                "last_error_category": None, "cycles": 0}
    row = db.get(WorkerHeartbeat, COMPONENT)
    if row is None:
        return {"state": "unknown", "last_seen_at": None, "last_success_at": None,
                "last_error_category": None, "cycles": 0}
    now = safe_now(now)
    # PostgreSQL returns timestamptz in the connection's configured timezone;
    # SQLite returns naive datetimes. safe_now converts aware values to UTC and
    # interprets SQLite's naive UTC storage convention explicitly.
    last_seen = safe_now(row.last_seen_at)
    last_success = safe_now(row.last_success_at) if row.last_success_at is not None else None
    threshold = max(60, notification_settings.worker_poll_seconds * 3)
    recent = now - last_seen <= timedelta(seconds=threshold)
    state = ("stale" if not recent else
             "degraded" if row.last_error_category is not None else "available")
    return {"state": state, "last_seen_at": last_seen.isoformat(),
            "last_success_at": last_success.isoformat() if last_success else None,
            "last_error_category": row.last_error_category, "cycles": row.cycle_count}


def overview(db, now: datetime, window_days: int, notification_settings) -> dict:
    since = now - timedelta(days=window_days)
    session_now = int(now.timestamp())
    notification_counts = {name: 0 for name in ("queued", "sending", "accepted", "failed", "cancelled")}
    for state, count in db.execute(select(NotificationDelivery.delivery_state, func.count())
                                   .group_by(NotificationDelivery.delivery_state)):
        if state in notification_counts:
            notification_counts[state] += int(count)
        elif state == "platform_accepted":
            notification_counts["accepted"] += int(count)
    pending = notification_counts["queued"] + notification_counts["sending"]
    oldest = db.scalar(select(func.min(NotificationDelivery.created_at)).where(
        NotificationDelivery.delivery_state.in_(["queued", "sending"])))
    if oldest is not None and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    oldest_pending_age = max(0, int((now - oldest).total_seconds())) if oldest is not None else None
    stale_sending = _count(db, select(func.count()).select_from(NotificationDelivery).where(
        NotificationDelivery.delivery_state == "sending",
        NotificationDelivery.lease_until.is_not(None),
        NotificationDelivery.lease_until < now,
    ))
    error_rows = db.execute(select(NotificationDelivery.error_code, func.count())
                            .where(NotificationDelivery.delivery_state == "failed",
                                   NotificationDelivery.error_code.is_not(None))
                            .group_by(NotificationDelivery.error_code)).all()
    error_counts: dict[str, int] = {}
    for code, count in error_rows:
        category = safe_error_category(code) or "other"
        error_counts[category] = error_counts.get(category, 0) + int(count)
    worker = _worker_state(db, notification_settings, now)
    return {
        "window_days": window_days,
        "accounts": {
            "total": _count(db, select(func.count()).select_from(User)),
            "registered_in_window": _count(db, select(func.count()).select_from(User).where(User.created_at >= since)),
            "deletions_in_window": None,
            "deletions_available": False,
            "deletions_reason": "Hard deletion leaves no retained account-linked event; deletions are not measured.",
            "recently_refreshed_v2_session_accounts": _count(db, select(func.count(distinct(AuthSession.user_id))).where(
                AuthSession.revoked_at.is_(None), AuthSession.current_generation > 0,
                AuthSession.last_refreshed_at >= int(since.timestamp()),
                AuthSession.idle_expires_at > session_now, AuthSession.absolute_expires_at > session_now)),
            "recent_session_window_days": window_days,
        },
        "obligations_total": _count(db, select(func.count()).select_from(Obligation)),
        "notifications": {
            "queue_size": pending,
            "pending": pending,
            "accepted": notification_counts["accepted"],
            "failed": notification_counts["failed"],
            "cancelled": notification_counts["cancelled"],
            "oldest_pending_age_seconds": oldest_pending_age,
            "stale_sending_count": stale_sending,
            "failed_error_categories": [{"category": category, "count": count}
                                        for category, count in sorted(error_counts.items(), key=lambda item: (-item[1], item[0]))[:10]],
        },
        "worker": worker,
    }


def system_health(db, request, now: datetime) -> dict:
    try:
        apply_read_timeout(db)
        db.execute(text("SELECT 1"))
        database = "available"
        try:
            migration = db.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
            migration_state = "available" if migration else "unknown"
        except SQLAlchemyError:
            db.rollback()
            migration, migration_state = None, "unknown"
    except SQLAlchemyError:
        db.rollback()
        database, migration, migration_state = "unavailable", None, "unavailable"
    try:
        request.app.state.security.limiter.store.ping()
        redis = "available"
    except Exception:
        redis = "unavailable"
    notification_settings = request.app.state.notification_settings
    config = {
        "admin_api_enabled": request.app.state.admin_settings.enabled,
        "admin_totp_key_configured": bool(request.app.state.admin_settings.totp_encryption_key),
        "durable_sessions_enabled": request.app.state.sessions.settings.enabled,
        "legacy_token_issuance_enabled": request.app.state.sessions.settings.legacy_issuance,
        "rate_limit_backend": request.app.state.security.settings.backend,
        "redis_endpoint_configured": bool(request.app.state.security.settings.redis_url),
        "notifications_enabled": notification_settings.enabled,
        "notification_delivery_enabled": notification_settings.delivery_enabled,
    }
    worker = _worker_state(db, notification_settings, now) if database == "available" else {
        "state": "unknown", "last_seen_at": None, "last_success_at": None,
        "last_error_category": None, "cycles": 0,
    }
    components = {"api": "available", "database": database, "redis": redis,
                  "notification_worker": worker["state"], "migration": migration_state}
    overall = "available" if all(value in {"available", "disabled"} for value in components.values()) else "degraded"
    return {"status": overall, "components": components, "configuration_readiness": config,
            "migration_revision": migration, "worker": worker}
