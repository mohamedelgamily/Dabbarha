from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.notification_copy import COPY_VERSION, render_copy
from app.models.auth_session import AuthSession
from app.models.notifications import (
    Notification, NotificationDelivery, NotificationPreference, PushDevice,
)
from app.models.user import User
from app.schemas.notifications import (
    NotificationPage, NotificationPreferencesResponse, NotificationPreferencesUpdate,
    NotificationResponse, PushDeviceCreate, PushDeviceResponse,
)
from app.services.notifications import (
    cancel_user_reminders, get_preferences, register_device, require_enabled,
)

router = APIRouter()


def _session_id(request: Request) -> str:
    payload = getattr(request.state, "auth_payload", {})
    if payload.get("ver") != 2 or not isinstance(payload.get("sid"), str):
        raise HTTPException(409, "Sign in with a device session before registering push notifications.")
    return payload["sid"]


def _enabled(request: Request):
    settings = request.app.state.notification_settings
    require_enabled(settings)
    return settings


@router.get("/preferences", response_model=NotificationPreferencesResponse)
def read_preferences(request: Request, current_user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    _enabled(request)
    row = get_preferences(db, current_user.id)
    db.commit()
    db.refresh(row)
    return row


@router.put("/preferences", response_model=NotificationPreferencesResponse)
def update_preferences(body: NotificationPreferencesUpdate, request: Request,
                       current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _enabled(request)
    row = get_preferences(db, current_user.id)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    cancel_user_reminders(db, current_user.id)
    try:
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return row


@router.post("/devices", response_model=PushDeviceResponse, status_code=201)
def create_device(body: PushDeviceCreate, request: Request,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = _enabled(request)
    session_id = _session_id(request)
    try:
        device = register_device(db, settings, user_id=current_user.id, session_id=session_id,
                                 token=body.token, platform=body.platform)
        db.commit()
        db.refresh(device)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    return device


@router.get("/devices", response_model=list[PushDeviceResponse])
def list_devices(request: Request, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    _enabled(request)
    return list(db.scalars(select(PushDevice).where(
        PushDevice.user_id == current_user.id,
    ).order_by(PushDevice.created_at.desc(), PushDevice.id)).all())


@router.put("/devices/{device_id}", response_model=PushDeviceResponse)
def rotate_device_token(device_id: int, body: PushDeviceCreate, request: Request,
                        current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = _enabled(request)
    session_id = _session_id(request)
    existing = db.scalar(select(PushDevice).where(
        PushDevice.id == device_id, PushDevice.user_id == current_user.id,
    ).with_for_update())
    if existing is None:
        raise HTTPException(404, "Device registration not found.")
    try:
        replacement = register_device(db, settings, user_id=current_user.id, session_id=session_id,
                                      token=body.token, platform=body.platform)
        if replacement.id != existing.id:
            existing.active = False
            db.execute(update(NotificationDelivery).where(
                NotificationDelivery.device_id == existing.id,
                NotificationDelivery.delivery_state.in_(["queued", "sending"]),
            ).values(delivery_state="cancelled", error_code="device_token_rotated"))
        db.commit()
        db.refresh(replacement)
    except Exception:
        db.rollback()
        raise
    return replacement


@router.delete("/devices/{device_id}", status_code=204)
def deactivate_device(device_id: int, request: Request,
                      current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _enabled(request)
    device = db.scalar(select(PushDevice).where(
        PushDevice.id == device_id, PushDevice.user_id == current_user.id,
    ).with_for_update())
    if device is None:
        raise HTTPException(404, "Device registration not found.")
    device.active = False
    db.execute(update(NotificationDelivery).where(
        NotificationDelivery.device_id == device_id,
        NotificationDelivery.delivery_state.in_(["queued", "sending"]),
    ).values(delivery_state="cancelled", error_code="device_deactivated", lease_until=None))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return Response(status_code=204)


@router.get("", response_model=NotificationPage)
def list_notifications(request: Request, current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db),
                       before_id: Annotated[int | None, Query(ge=1)] = None,
                       limit: Annotated[int, Query(ge=1, le=100)] = 50):
    _enabled(request)
    query = select(Notification).where(Notification.user_id == current_user.id)
    if before_id is not None:
        query = query.where(Notification.id < before_id)
    rows = list(db.scalars(query.order_by(Notification.id.desc()).limit(limit + 1)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    unread = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == current_user.id, Notification.read_at.is_(None))) or 0
    return NotificationPage(items=rows,
                            next_before_id=rows[-1].id if has_more and rows else None,
                            unread_count=unread)


@router.get("/unread-count")
def unread_count(request: Request, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    _enabled(request)
    count = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == current_user.id, Notification.read_at.is_(None))) or 0
    return {"unread_count": count}


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(notification_id: int, request: Request,
              current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _enabled(request)
    row = db.scalar(select(Notification).where(
        Notification.id == notification_id, Notification.user_id == current_user.id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "Notification not found.")
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        try:
            db.commit()
            db.refresh(row)
        except Exception:
            db.rollback()
            raise
    return row
