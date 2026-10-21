from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import DATABASE_URL


def create_app_engine(url: str, **kwargs: Any) -> Engine:
    """Apply SQLite integrity policy to every newly opened application connection."""
    connect_args = kwargs.pop("connect_args", {})
    if url.startswith("sqlite"):
        connect_args.setdefault("check_same_thread", False)
    kwargs.setdefault("hide_parameters", True)
    result = create_engine(url, connect_args=connect_args, **kwargs)
    if result.dialect.name == "sqlite":
        @event.listens_for(result, "connect")
        def enable_foreign_keys(connection, _record):
            # PRAGMA is ineffective inside a transaction; account for modern
            # sqlite3 autocommit modes as well as Python 3.12's legacy default.
            has_autocommit = hasattr(connection, "autocommit")
            if has_autocommit:
                previous = connection.autocommit
                connection.autocommit = True
            try:
                cursor = connection.cursor()
                try:
                    cursor.execute("PRAGMA foreign_keys=ON")
                finally:
                    cursor.close()
            finally:
                if has_autocommit:
                    connection.autocommit = previous
    return result


engine = create_app_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
