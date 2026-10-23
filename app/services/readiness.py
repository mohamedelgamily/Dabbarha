"""Low-detail, read-only dependency readiness checks for infrastructure probes."""
from functools import lru_cache
from pathlib import Path
import threading

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

_probe_slot = threading.BoundedSemaphore(1)


@lru_cache(maxsize=1)
def expected_migration_heads() -> frozenset[str]:
    project_root = Path(__file__).resolve().parents[2]
    script = ScriptDirectory.from_config(Config(str(project_root / "alembic.ini")))
    return frozenset(script.get_heads())


def check_readiness(db, security, *, require_postgres: bool = False) -> bool:
    """Return only ready/unavailable; never return driver or infrastructure details."""
    try:
        expected = expected_migration_heads()
        if not expected:
            return False
        database_dialect = db.get_bind().dialect.name
        if require_postgres and database_dialect != "postgresql":
            return False
        if database_dialect == "postgresql":
            # Checkout/connect bounds come from the application engine; bound
            # the two read-only SQL statements separately as well.
            db.execute(text("SET LOCAL statement_timeout = '1500ms'"))
            db.execute(text("SET LOCAL lock_timeout = '1000ms'"))
        if db.execute(text("SELECT 1")).scalar_one() != 1:
            return False
        applied = frozenset(db.scalars(text("SELECT version_num FROM alembic_version")).all())
        if applied != expected:
            return False
        if security.settings.backend == "redis":
            security.limiter.store.ping()
        return True
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return False


def probe_readiness(db, security, *, require_postgres: bool = False) -> bool:
    """Allow one concurrent dependency probe per API process."""
    if not _probe_slot.acquire(blocking=False):
        return False
    try:
        return check_readiness(db, security, require_postgres=require_postgres)
    finally:
        _probe_slot.release()
