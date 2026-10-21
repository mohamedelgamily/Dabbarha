"""Offline, interactive administrator provisioning/revocation command.

Never run this from a web request. Provisioning prints the new factor secret once.
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone

from sqlalchemy import select, update, text

from app.core.admin_settings import decode_totp_encryption_key
from app.db.database import SessionLocal
from app.models.admin_audit import AdminAuditEvent
from app.models.auth_session import AuthRefreshToken, AuthSession
from app.models.user import User
from app.services.admin_security import encrypt_totp_secret, generate_totp_secret, provisioning_uri


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision or revoke Dabbarha administrator MFA offline.")
    sub = parser.add_subparsers(dest="operation", required=True)
    provision = sub.add_parser("provision", help="Promote an existing account and enroll a TOTP factor.")
    provision.add_argument("--user-id", type=int, required=True)
    provision.add_argument("--role", choices=("admin", "superadmin"), required=True)
    revoke = sub.add_parser("revoke", help="Remove administrator privileges and the enrolled TOTP factor.")
    revoke.add_argument("--user-id", type=int, required=True)
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        parser.error("DATABASE_URL must be explicitly set to the intended database before changing administrator access.")
    if not os.environ.get("ADMIN_TOTP_ENCRYPTION_KEY"):
        parser.error("ADMIN_TOTP_ENCRYPTION_KEY must be supplied through the trusted process environment.")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("Administrator provisioning must run directly in an interactive terminal.")
    key_id = os.environ.get("ADMIN_TOTP_KEY_ID", "v1")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", key_id):
        parser.error("ADMIN_TOTP_KEY_ID must be 1–32 ASCII letters, digits, underscores or hyphens.")
    action_label = "PROVISION" if args.operation == "provision" else "REVOKE"
    expected = f"{action_label} ADMIN {args.user_id}"
    if input(f"Type '{expected}' to continue: ").strip() != expected:
        parser.error("Confirmation did not match; no administrator change was made.")
    key = decode_totp_encryption_key(os.environ)
    session = SessionLocal()
    secret = None
    try:
        with session.begin():
            if session.bind.dialect.name == "sqlite":
                # Acquire the SQLite write reservation before inspecting role state.
                session.execute(text("BEGIN IMMEDIATE"))
            user = session.scalar(select(User).where(User.id == args.user_id).with_for_update())
            if user is None:
                parser.error("The selected account does not exist.")
            if args.operation == "provision":
                if user.admin_role != "user":
                    parser.error("The selected account already has administrator state; use a reviewed recovery procedure.")
                secret = generate_totp_secret()
                settings = type("OfflineKeySettings", (), {"totp_encryption_key": key,
                    "totp_key_id": key_id})()
                nonce, ciphertext = encrypt_totp_secret(secret, user.id, settings)
                user.admin_role = args.role
                user.admin_totp_nonce, user.admin_totp_ciphertext = nonce, ciphertext
                user.admin_totp_key_id = settings.totp_key_id
                user.admin_totp_last_step = None
                action, outcome = "admin_role_provisioned", "success"
            else:
                if user.admin_role == "user":
                    parser.error("The selected account is not an administrator.")
                user.admin_role = "user"
                user.admin_totp_nonce = user.admin_totp_ciphertext = None
                user.admin_totp_key_id = None
                user.admin_totp_last_step = None
                action, outcome = "admin_role_revoked", "success"
            now = int(datetime.now(timezone.utc).timestamp())
            session.execute(update(AuthSession).where(AuthSession.user_id == user.id,
                AuthSession.revoked_at.is_(None)).values(revoked_at=now, revocation_reason="admin_role_changed"))
            session.execute(update(AuthRefreshToken).where(AuthRefreshToken.session_id.in_(
                select(AuthSession.id).where(AuthSession.user_id == user.id))).values(
                    response_ciphertext=None, encryption_nonce=None, encryption_key_id=None))
            audit = AdminAuditEvent(actor_user_id=None, target_user_id=user.id,
                                    action=action, outcome=outcome)
            session.add(audit)
        if secret:
            print("TOTP enrollment URI (display once; never store in tickets or logs):")
            print(provisioning_uri(secret, "Dabbarha", user.email))
            print("If the URI cannot be imported, the one-time base32 seed is:")
            print(secret)
        else:
            print("Administrator privileges revoked.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
