"""TOTP enrollment, one-time step-up verification and credential-free audit helpers."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from Cryptodome.Cipher import AES
from fastapi import HTTPException, Request

from app.models.admin_audit import AdminAuditEvent
from app.models.user import User

TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** TOTP_DIGITS)
    return f"{value:0{TOTP_DIGITS}d}"


def matching_totp_step(secret: str, supplied: str, now: int, last_step: int | None) -> int | None:
    if len(supplied) != TOTP_DIGITS or not supplied.isascii() or not supplied.isdigit():
        return None
    current = now // TOTP_PERIOD_SECONDS
    matches = [step for step in (current - 1, current, current + 1)
               if step > (last_step if last_step is not None else -1)
               and hmac.compare_digest(totp_code(secret, step), supplied)]
    return max(matches) if matches else None


def encrypt_totp_secret(secret: str, user_id: int, settings) -> tuple[bytes, bytes]:
    nonce = secrets.token_bytes(12)
    aad = f"dabbarha-admin-totp-v1:{settings.totp_key_id}:{user_id}".encode("ascii")
    cipher = AES.new(settings.totp_encryption_key, AES.MODE_GCM, nonce=nonce, mac_len=16)
    cipher.update(aad)
    return nonce, cipher.encrypt_and_digest(secret.encode("ascii"))[0] + cipher.digest()


def decrypt_totp_secret(nonce: bytes, ciphertext: bytes, user_id: int, settings, key_id: str | None = None) -> str:
    if len(ciphertext) < 17:
        raise ValueError("Invalid encrypted TOTP secret")
    aad = f"dabbarha-admin-totp-v1:{key_id or settings.totp_key_id}:{user_id}".encode("ascii")
    cipher = AES.new(settings.totp_encryption_key, AES.MODE_GCM, nonce=nonce, mac_len=16)
    cipher.update(aad)
    return cipher.decrypt_and_verify(ciphertext[:-16], ciphertext[-16:]).decode("ascii")


def provisioning_uri(secret: str, issuer: str, account: str) -> str:
    label = quote(f"{issuer}:{account}", safe="")
    return (f"otpauth://totp/{label}?secret={quote(secret)}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD_SECONDS}")


def audit_source(source: str | None, key: bytes) -> str | None:
    if not source:
        return None
    return hmac.new(key, b"admin-audit-source-v1\0" + source.encode("utf-8", "replace"), hashlib.sha256).hexdigest()


def write_audit(db, key: bytes, action: str, outcome: str, actor_id: int | None = None,
                target_id: int | None = None, source: str | None = None) -> None:
    db.add(AdminAuditEvent(actor_user_id=actor_id, target_user_id=target_id, action=action,
                           outcome=outcome, source_fingerprint=audit_source(source, key)))


def require_admin_api(request: Request):
    if not request.app.state.admin_settings.enabled:
        raise HTTPException(404, "Not found")


def require_admin_stepup(request: Request, user: User) -> dict:
    require_admin_api(request)
    payload = request.state.auth_payload
    now = int(time.time())
    try:
        valid = (payload.get("ver") == 2 and payload.get("token_use") == "admin_stepup"
                 and type(payload.get("admin_mfa_at")) is int
                 and 0 <= now - payload["admin_mfa_at"] <= request.app.state.admin_settings.max_stepup_age_seconds
                 and payload.get("admin_role") in {"admin", "superadmin"}
                 and user.admin_role == payload.get("admin_role"))
    except (TypeError, KeyError):
        valid = False
    if not valid:
        raise HTTPException(403, "Administrator MFA verification is required.")
    return payload
