"""Bounded per-account lock shared by account deletion and notification sends."""
from sqlalchemy import text, update

from app.models.user import User

ACCOUNT_OPERATION_LOCK_TIMEOUT_SECONDS = 8


def lock_account_row(db, user_id: int) -> bool:
    """Acquire a write/row lock or return False if the account no longer exists.

    Call inside a transaction. SQLite serializes writers; PostgreSQL takes a row
    lock. The lock wait is bounded, and callers must rollback on database errors.
    """
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"),
                   {"timeout": f"{ACCOUNT_OPERATION_LOCK_TIMEOUT_SECONDS}s"})
    elif dialect == "sqlite":
        db.execute(text(f"PRAGMA busy_timeout={ACCOUNT_OPERATION_LOCK_TIMEOUT_SECONDS * 1000}"))
    else:
        raise RuntimeError("Unsupported database for account-operation locking.")

    changed = db.execute(update(User).where(User.id == user_id).values(name=User.name)).rowcount
    return changed == 1
