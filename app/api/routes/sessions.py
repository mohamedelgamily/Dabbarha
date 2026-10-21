"""Explicitly versioned-by-contract device sessions alongside legacy login."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, oauth2_scheme
from app.core.api_security import source_ip
from app.core.security import DUMMY_PASSWORD_HASH, decode_access_token, verify_password
from app.models.auth_session import AuthSession
from app.models.user import User
from app.schemas.sessions import LogoutRequest, RefreshRequest, RevokeRequest, SessionLogin, SessionSummary, SessionToken
from app.services.sessions import unauthorized

router = APIRouter()


def password_check(request, email, password, user):
    runtime = request.app.state.security
    reservation = runtime.login_reserve(email, source_ip(request.scope))
    try:
        with runtime.password_slot():
            verified = verify_password(password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    except Exception:
        runtime.limiter.release(reservation)
        raise
    if user is None or not verified:
        raise HTTPException(401, "Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
    runtime.limiter.release(reservation)


@router.post("/sessions", response_model=SessionToken)
def create_session(body: SessionLogin, request: Request, db: Session = Depends(get_db)):
    service = request.app.state.sessions
    service.require_enabled()
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    password_check(request, email, body.password, user)
    uid, bind = user.id, db.get_bind()
    # End the read-only credential lookup before owning a new short lifecycle transaction.
    db.rollback()
    return service.create(bind, uid, body.device_label)


@router.post("/refresh", response_model=SessionToken)
def refresh(body: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    return request.app.state.sessions.refresh(db.get_bind(), body.refresh_token, body.retry_key,
                                             request.app.state.security.refresh_session)


def session_identity(request: Request, token: str = Depends(oauth2_scheme), user: User = Depends(get_current_user)):
    request.app.state.sessions.require_enabled()
    payload = request.state.auth_payload
    if payload.get("ver") != 2:
        raise unauthorized()
    return user, payload["sid"]


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(request: Request, identity=Depends(session_identity), db: Session = Depends(get_db),
                  offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
                  limit: Annotated[int, Query(ge=1, le=100)] = 50):
    user, sid = identity
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id).order_by(
        AuthSession.created_at.desc(), AuthSession.id).offset(offset).limit(limit)).all()
    return [SessionSummary(**{key: getattr(row, key) for key in SessionSummary.model_fields if key != "current"},
                           current=row.id == sid) for row in rows]


@router.post("/sessions/{sid}/revoke", status_code=204)
def revoke_session(sid: UUID, body: RevokeRequest, request: Request,
                   identity=Depends(session_identity), db: Session = Depends(get_db)):
    user, _ = identity
    password_check(request, user.email, body.password, user)
    uid, bind = user.id, db.get_bind()
    db.rollback()
    request.app.state.sessions.revoke(bind, str(sid), uid)
    return Response(status_code=204)


@router.post("/logout", status_code=204)
def logout(request: Request, body: LogoutRequest | None = None,
           authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    service = request.app.state.sessions
    service.require_enabled()
    if (body is None) == (authorization is None):
        raise HTTPException(422, "Provide exactly one credential: bearer access token or refresh token.")
    if body is not None:
        service.logout_refresh(db.get_bind(), body.refresh_token, request.app.state.security.refresh_session)
    else:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise unauthorized()
        try:
            payload = decode_access_token(token)
            uid = int(payload["sub"])
            if not 0 < uid <= 9223372036854775807:
                raise ValueError()
        except (jwt.PyJWTError, ValueError, TypeError):
            raise unauthorized() from None
        service.logout_access(db.get_bind(), payload, token,
                              lambda user_id: request.app.state.security.financial(request, user_id, force=True))
    return Response(status_code=204)
