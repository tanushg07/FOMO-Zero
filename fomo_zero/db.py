from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine, create_engine as sqlalchemy_create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def create_engine(database_url: str = "sqlite:///fomo_zero.db") -> Engine:
    """Create an engine and enforce SQLite foreign keys on every connection."""
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = sqlalchemy_create_engine(database_url, connect_args=connect_args)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    from . import models  # noqa: F401

    if engine.url.database and engine.url.database != ":memory:":
        Path(engine.url.database).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
