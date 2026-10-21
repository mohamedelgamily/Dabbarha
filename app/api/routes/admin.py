"""Phase 2f.1 administrator authentication only; operational APIs follow later."""
import time
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, text

from app.api.deps import get_current_user, get_db
from app.api.routes.sessions import session_identity
from app.core.config import JWT_ALGORITHM, JWT_SECRET_KEY
from app.core.api_security import source_ip
from app.models.user import User
from app.schemas.admin import AdminStepUpRequest, AdminStepUpResponse
from app.services.admin_security import (
    decrypt_totp_secret, matching_totp_step, require_admin_api, require_admin_stepup, write_audit,
)

router = APIRouter(dependencies=[Depends(require_admin_api)])


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
def admin_identity(user: User = Depends(get_current_user), stepup=Depends(require_stepup)):
    # A deliberately minimal probe for clients; no email, password or factor material.
    return {"admin_role": user.admin_role, "step_up_expires_at": stepup["exp"]}
