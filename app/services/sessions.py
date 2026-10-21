"""Durable session authority and bounded encrypted rotation receipts.

Each mutation owns a short transaction, independent of request/financial transactions.
HTTP replay rejection is raised AFTER a revocation transaction has committed.
"""
from contextlib import contextmanager
import hashlib
import hmac
import json
import secrets
import time
from uuid import uuid4

from app.core.receipts import ReceiptCipher
from fastapi import HTTPException
import jwt
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from app.core.config import JWT_ALGORITHM, JWT_SECRET_KEY
from app.models.auth_session import AuthRefreshToken, AuthSession, LegacyAccessRevocation


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def fingerprint(token: str) -> str:
    # Call ONLY after verifying signature/claims. Normalize signature encoding.
    signing_input, signature = token.rsplit(".", 1)
    return hashlib.sha256(signing_input.encode("ascii") + b"\0" + jwt.utils.base64url_decode(signature)).hexdigest()


def unauthorized():
    return HTTPException(401, "Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})


def unavailable():
    return HTTPException(503, "Session security is temporarily unavailable. Please try again.", headers={"Retry-After": "1"})


class SessionService:
    def __init__(self, settings, clock=time.time):
        self.settings = settings
        self.clock = clock

    def require_enabled(self):
        if not self.settings.enabled:
            raise HTTPException(503, "Device sessions are not enabled.")

    @contextmanager
    def transaction(self, bind):
        self.require_enabled()
        with Session(bind=bind, expire_on_commit=False) as db:
            try:
                if bind.dialect.name == "sqlite":
                    # SQLite ignores FOR UPDATE. Acquire the write reservation BEFORE reads.
                    db.execute(text(f"PRAGMA busy_timeout={self.settings.lock_timeout_seconds * 1000}"))
                    db.execute(text("BEGIN IMMEDIATE"))
                elif bind.dialect.name == "postgresql":
                    db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"),
                               {"timeout": f"{self.settings.lock_timeout_seconds}s"})
                else:
                    raise RuntimeError("Unsupported session database")
                yield db
                db.commit()
            except HTTPException:
                db.rollback()
                raise
            except Exception:
                # Never leak driver/AEAD exceptions, SQL parameters or credentials.
                db.rollback()
                raise unavailable() from None

    def active(self, session, now):
        return (session is not None and session.revoked_at is None
                and now < session.idle_expires_at and now < session.absolute_expires_at)

    def authorize(self, db, payload, token):
        if not self.settings.enabled:
            if payload.get("ver") == 2 or not self.settings.legacy_acceptance:
                raise unauthorized()
            return
        try:
            if payload.get("ver") == 2:
                row = db.get(AuthSession, payload["sid"])
                if not self.active(row, int(self.clock())) or row.user_id != int(payload["sub"]):
                    raise unauthorized()
            elif not self.settings.legacy_acceptance or db.get(LegacyAccessRevocation, fingerprint(token)):
                raise unauthorized()
        except HTTPException:
            raise
        except Exception:
            raise unavailable() from None

    def pair(self, session, refresh, now):
        expiry = min(now + self.settings.access_minutes * 60, session.idle_expires_at, session.absolute_expires_at)
        access = jwt.encode({"sub": str(session.user_id), "sid": session.id, "jti": str(uuid4()),
                             "iat": now, "exp": expiry, "token_use": "access", "ver": 2},
                            JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return {"access_token": access, "token_type": "bearer", "expires_in": expiry - now,
                "refresh_token": refresh, "refresh_expires_at": session.idle_expires_at,
                "session_id": session.id, "session_expires_at": session.absolute_expires_at}

    def create(self, bind, user_id, label):
        with self.transaction(bind) as db:
            now = int(self.clock())
            refresh = secrets.token_urlsafe(32)
            row = AuthSession(id=str(uuid4()), user_id=user_id, device_label=label, created_at=now,
                              last_refreshed_at=now, idle_expires_at=now + self.settings.idle_days * 86400,
                              absolute_expires_at=now + self.settings.absolute_days * 86400,
                              current_refresh_hash=digest(refresh), current_generation=0)
            db.add(row)
            db.flush()  # Parent exists before FK history insertion, without ORM relationships.
            db.add(AuthRefreshToken(token_hash=row.current_refresh_hash, session_id=row.id, generation=0,
                                    issued_at=now, expires_at=row.idle_expires_at, recovery_count=0))
            result = self.pair(row, refresh, now)
        return result

    @staticmethod
    def clear_receipt(row):
        row.response_ciphertext = row.encryption_nonce = row.encryption_key_id = None

    def revoke_locked(self, db, row, now, reason):
        if row.revoked_at is None:
            row.revoked_at, row.revocation_reason = now, reason
        db.execute(update(AuthRefreshToken).where(AuthRefreshToken.session_id == row.id).values(
            response_ciphertext=None, encryption_nonce=None, encryption_key_id=None))

    @staticmethod
    def aad(row):
        return json.dumps(["dabbarha-refresh-receipt-v1", row.session_id, row.token_hash, row.generation,
                           row.retry_key_hash, row.successor_token_hash, row.recovery_expires_at,
                           row.encryption_key_id], separators=(",", ":")).encode("ascii")

    def refresh(self, bind, refresh, retry_key, admit=lambda _sid: None):
        result, rejection = None, None
        with self.transaction(bind) as db:
            token_hash = digest(refresh)
            sid = db.scalar(select(AuthRefreshToken.session_id).where(AuthRefreshToken.token_hash == token_hash))
            if sid is None:
                raise unauthorized()
            admit(sid)  # Server-resolved identity only; Redis remains quota authority.
            session = db.scalar(select(AuthSession).where(AuthSession.id == sid).with_for_update())
            row = db.get(AuthRefreshToken, token_hash)
            now = int(self.clock())  # Re-check deadlines after waiting for the session lock.
            if not self.active(session, now):
                raise unauthorized()
            key_hash = digest(retry_key)
            if row.consumed_at is not None:
                matching = hmac.compare_digest(row.retry_key_hash, key_hash)
                if matching:
                    if (now >= row.recovery_expires_at or row.recovery_count >= self.settings.recovery_retries
                        or session.current_refresh_hash != row.successor_token_hash):
                        self.clear_receipt(row)
                        rejection = HTTPException(409, "refresh_recovery_unavailable")
                    else:
                        if (row.encryption_key_id != self.settings.receipt_key_id
                            or row.response_ciphertext is None or row.encryption_nonce is None):
                            raise unavailable()
                        plaintext = ReceiptCipher(self.settings.receipt_key).decrypt(
                            row.encryption_nonce, row.response_ciphertext, self.aad(row))
                        result = json.loads(plaintext)
                        row.recovery_count += 1
                        if row.recovery_count == self.settings.recovery_retries:
                            self.clear_receipt(row)
                elif now < row.recovery_expires_at:
                    rejection = HTTPException(409, "refresh_conflict")
                else:
                    self.revoke_locked(db, session, now, "refresh_reuse")
                    rejection = unauthorized()
            else:
                if now >= row.expires_at or session.current_refresh_hash != token_hash:
                    raise unauthorized()
                # Consuming this successor invalidates any predecessor receipt immediately.
                db.execute(update(AuthRefreshToken).where(AuthRefreshToken.session_id == sid,
                    AuthRefreshToken.response_ciphertext.is_not(None)).values(
                        response_ciphertext=None, encryption_nonce=None, encryption_key_id=None))
                successor = secrets.token_urlsafe(32)
                row.consumed_at, row.retry_key_hash = now, key_hash
                row.successor_token_hash = digest(successor)
                row.recovery_expires_at = now + self.settings.recovery_seconds
                row.recovery_count = 0
                session.current_generation += 1
                session.current_refresh_hash = row.successor_token_hash
                session.last_refreshed_at = now
                session.idle_expires_at = min(now + self.settings.idle_days * 86400, session.absolute_expires_at)
                db.add(AuthRefreshToken(token_hash=row.successor_token_hash, session_id=sid,
                    generation=session.current_generation, issued_at=now, expires_at=session.idle_expires_at,
                    recovery_count=0))
                result = self.pair(session, successor, now)
                row.encryption_key_id = self.settings.receipt_key_id
                row.encryption_nonce = secrets.token_bytes(12)
                row.response_ciphertext = ReceiptCipher(self.settings.receipt_key).encrypt(
                    row.encryption_nonce, json.dumps(result, separators=(",", ":")).encode("ascii"), self.aad(row))
        if rejection:
            raise rejection  # In particular, do not roll back committed reuse revocation.
        return result

    def logout_refresh(self, bind, token, admit=lambda _sid: None):
        with self.transaction(bind) as db:
            sid = db.scalar(select(AuthRefreshToken.session_id).where(AuthRefreshToken.token_hash == digest(token)))
            if sid is not None:
                admit(sid)
                row = db.scalar(select(AuthSession).where(AuthSession.id == sid).with_for_update())
                self.revoke_locked(db, row, int(self.clock()), "logout")

    def logout_access(self, bind, payload, token, admit=lambda _uid: None):
        with self.transaction(bind) as db:
            uid = int(payload["sub"])
            admit(uid)
            now = int(self.clock())
            if payload.get("ver") == 2:
                row = db.scalar(select(AuthSession).where(AuthSession.id == payload["sid"]).with_for_update())
                if row is None or row.user_id != uid:
                    raise unauthorized()
                self.revoke_locked(db, row, now, "logout")
            else:
                # User-row lock serializes repeated legacy logout; prevents duplicate PK races.
                from app.models.user import User
                if db.scalar(select(User).where(User.id == uid).with_for_update()) is None:
                    raise unauthorized()
                key = fingerprint(token)
                if db.get(LegacyAccessRevocation, key) is None:
                    db.add(LegacyAccessRevocation(fingerprint=key, user_id=uid, revoked_at=now, expires_at=int(payload["exp"])))

    def revoke(self, bind, sid, user_id):
        with self.transaction(bind) as db:
            row = db.scalar(select(AuthSession).where(AuthSession.id == sid, AuthSession.user_id == user_id).with_for_update())
            if row is None:
                raise HTTPException(404, "Session not found.")
            self.revoke_locked(db, row, int(self.clock()), "device_revocation")

    def cleanup(self, bind, batch_size=500):
        """Bounded maintenance; consumed hashes survive until family absolute expiry."""
        with self.transaction(bind) as db:
            now = int(self.clock())
            rows = db.scalars(select(AuthSession).order_by(AuthSession.id).where(
                (AuthSession.absolute_expires_at <= now) | AuthSession.id.in_(select(AuthRefreshToken.session_id).where(
                    AuthRefreshToken.recovery_expires_at <= now, AuthRefreshToken.response_ciphertext.is_not(None)))
            ).limit(batch_size).with_for_update(skip_locked=True)).all()
            for row in rows:
                if row.absolute_expires_at <= now:
                    db.delete(row)
                else:
                    db.execute(update(AuthRefreshToken).where(AuthRefreshToken.session_id == row.id,
                        AuthRefreshToken.recovery_expires_at <= now).values(
                            response_ciphertext=None, encryption_nonce=None, encryption_key_id=None))
            keys = select(LegacyAccessRevocation.fingerprint).where(LegacyAccessRevocation.expires_at <= now).limit(batch_size)
            db.execute(delete(LegacyAccessRevocation).where(LegacyAccessRevocation.fingerprint.in_(keys)))
        return len(rows)
