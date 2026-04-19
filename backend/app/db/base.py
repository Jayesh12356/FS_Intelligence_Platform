"""SQLAlchemy async engine and session factory."""

import logging
from datetime import UTC, datetime

from sqlalchemy import DateTime, TypeDecorator
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = logging.getLogger(__name__)


class UtcDateTime(TypeDecorator):
    """DateTime column that guarantees tzinfo=UTC on both bind and load.

    SQLite — used in tests and in some dev environments — silently strips
    tzinfo even when the column declares ``timezone=True``. That produces
    two real problems:

    1. Pydantic responses serialize naive datetimes as ``"...Z"``-less
       strings, failing OpenAPI's declared ``format: "date-time"`` contract.
    2. Comparisons like ``row.expires_at < datetime.now(UTC)`` explode with
       ``TypeError: can't compare offset-naive and offset-aware datetimes``.

    Routing every ``DateTime(timezone=True)`` column through this decorator
    keeps the invariant "datetimes crossing the ORM boundary are UTC-aware"
    regardless of dialect.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


# Universal "naive → UTC" shim for loaded ORM instances. SQLite ignores
# ``DateTime(timezone=True)`` and returns naive datetimes, which breaks
# RFC 3339 serialization (OpenAPI ``format: "date-time"`` expects tzinfo)
# and ``datetime.now(UTC)`` comparisons. Postgres stores real TIMESTAMPTZ
# so this is a no-op there. The listener is wired to ``Base`` so it
# propagates to every mapped subclass without requiring per-column
# annotations across ~30 models.
from sqlalchemy import event  # noqa: E402


def _normalize_instance_datetimes(instance) -> None:
    try:
        mapper = type(instance).__mapper__
    except AttributeError:  # pragma: no cover — defensive
        return
    for column in mapper.columns:
        try:
            type_str = str(column.type).lower()
        except Exception:  # pragma: no cover
            continue
        if "timestamp" not in type_str and "datetime" not in type_str:
            continue
        value = getattr(instance, column.key, None)
        if isinstance(value, datetime) and value.tzinfo is None:
            setattr(instance, column.key, value.replace(tzinfo=UTC))


@event.listens_for(Base, "load", propagate=True)
def _normalize_on_load(instance, _context):
    _normalize_instance_datetimes(instance)


@event.listens_for(Base, "refresh", propagate=True)
def _normalize_on_refresh(instance, _context, _attrs):
    _normalize_instance_datetimes(instance)


def _build_engine():
    settings = get_settings()
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    connect_args = {}
    parsed = make_url(db_url)
    query = dict(parsed.query)
    sslmode = str(query.get("sslmode", "")).lower()
    if sslmode in {"require", "verify-ca", "verify-full"}:
        connect_args["ssl"] = "require"
        query.pop("sslmode", None)
        parsed = parsed.set(query=query)
        db_url = parsed.render_as_string(hide_password=False)

    # SQLite (and any driver using NullPool/StaticPool) rejects the
    # ``pool_size`` / ``max_overflow`` kwargs — they only apply to
    # QueuePool-based dialects like Postgres and MySQL. Detect the driver
    # up front so the engine builder works uniformly for production
    # (Postgres) and hermetic test runs (SQLite via aiosqlite).
    engine_kwargs: dict = {
        "echo": False,
        "connect_args": connect_args,
    }
    if not db_url.startswith("sqlite"):
        engine_kwargs.update(
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return create_async_engine(db_url, **engine_kwargs)


engine = _build_engine()

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Dependency — yields an async DB session.

    On clean exit we commit any active transaction. This covers endpoints
    that ``flush`` their writes without explicitly committing: after a
    flush the ``new``/``dirty``/``deleted`` sets are empty but a live
    transaction still wraps the SQL, so skipping commit would silently
    discard the changes on ``session.close``. Read-only paths that never
    begin a transaction return immediately from ``commit``.
    """
    async with async_session_factory() as session:
        try:
            yield session
            if session.in_transaction():
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
