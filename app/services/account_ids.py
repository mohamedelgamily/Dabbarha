"""Allocate non-repeating SQLite user IDs without retaining deleted identities."""
from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models.account_id_sequence import AccountIdSequence
from app.models.user import User


def allocate_sqlite_user_id(db) -> int:
    """Advance a global, PII-free high-water mark inside the registration transaction."""
    if db.get_bind().dialect.name != "sqlite":
        raise RuntimeError("SQLite account ID allocation used with another database.")

    current_max = db.scalar(select(func.coalesce(func.max(User.id), 0))) or 0
    db.execute(sqlite_insert(AccountIdSequence).values(id=1, last_id=current_max)
               .on_conflict_do_nothing(index_elements=["id"]))
    db.execute(update(AccountIdSequence).where(
        AccountIdSequence.id == 1,
        AccountIdSequence.last_id < current_max,
    ).values(last_id=current_max))
    allocated = db.execute(update(AccountIdSequence).where(
        AccountIdSequence.id == 1,
    ).values(last_id=AccountIdSequence.last_id + 1).returning(AccountIdSequence.last_id)).scalar_one()
    return int(allocated)


def advance_account_id_highwater(db, user_id: int) -> None:
    """Persist only the global maximum ID so a deleted SQLite row cannot be reused."""
    dialect = db.get_bind().dialect.name
    values = {"id": 1, "last_id": user_id}
    if dialect == "sqlite":
        insert = sqlite_insert(AccountIdSequence).values(**values)
    elif dialect == "postgresql":
        insert = pg_insert(AccountIdSequence).values(**values)
    else:
        raise RuntimeError("Unsupported database for account ID high-water mark.")
    excluded = insert.excluded
    db.execute(insert.on_conflict_do_update(
        index_elements=["id"],
        set_={"last_id": case(
            (AccountIdSequence.last_id < excluded.last_id, excluded.last_id),
            else_=AccountIdSequence.last_id,
        )},
    ))
