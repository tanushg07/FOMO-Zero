from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine, create_engine as sqlalchemy_create_engine, event, inspect, text
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
    _migrate_sqlite_schema(engine)


def _migrate_sqlite_schema(engine: Engine) -> None:
    """Apply additive migrations for existing local SQLite databases.

    The project does not yet use Alembic, so ``create_all`` alone cannot add
    columns to a database created by an earlier version.
    """
    if engine.dialect.name != "sqlite":
        return
    additions = {
        "notices": {"validation_reason": "TEXT"},
        "change_records": {
            "previous_evidence_text": "TEXT",
            "previous_evidence_start": "INTEGER",
            "previous_evidence_end": "INTEGER",
            "current_evidence_text": "TEXT",
            "current_evidence_start": "INTEGER",
            "current_evidence_end": "INTEGER",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in additions.items():
            if table not in inspector.get_table_names():
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for column, column_type in columns.items():
                if column not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))
