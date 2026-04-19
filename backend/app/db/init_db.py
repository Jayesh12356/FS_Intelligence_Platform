"""Database initialisation — creates tables and runs Alembic migrations on startup."""

from __future__ import annotations

import logging
from pathlib import Path

import anyio
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect, text

from alembic import command as alembic_command
from app.config import get_settings
from app.db import models  # noqa: F401 — register models
from app.db.base import Base, engine

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
BASELINE_REVISION = "0001_baseline"


def _alembic_cfg() -> AlembicConfig:
    cfg = AlembicConfig(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    settings = get_settings()
    sync_url = settings.DATABASE_URL_SYNC or settings.DATABASE_URL
    if sync_url.startswith("postgresql+asyncpg://"):
        sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    cfg.set_main_option("sqlalchemy.url", sync_url)
    return cfg


def _run_alembic_sync() -> None:
    cfg = _alembic_cfg()

    from sqlalchemy import create_engine

    sync_url = cfg.get_main_option("sqlalchemy.url")
    if not sync_url:
        logger.warning("Alembic: no sync URL configured; skipping migrations.")
        return
    sync_engine = create_engine(sync_url, future=True)
    try:
        with sync_engine.connect() as conn:
            insp = inspect(conn)
            tables = set(insp.get_table_names())
            has_alembic = "alembic_version" in tables
            has_domain_tables = any(t in tables for t in {"fs_documents", "fs_tasks"})
            if has_domain_tables and not has_alembic:
                # Two sub-cases distinguished by whether ``create_all`` (run
                # immediately before us) just created a *fresh* schema that
                # already matches ``head`` of Alembic, or whether we're
                # adopting an existing legacy DB that pre-dates Alembic.
                #
                # The current model includes columns added by migrations
                # 0002 / 0003 / etc. — if those columns are already present
                # the table was just created by ``Base.metadata.create_all``
                # and re-applying the migrations would crash with
                # ``DuplicateColumn``. Detect this and stamp ``head``
                # instead of ``baseline``.
                fresh_install = False
                try:
                    cols = {c["name"] for c in insp.get_columns("ambiguity_flags")}
                    fresh_install = "resolution_text" in cols
                except Exception:  # pragma: no cover — table missing is OK
                    fresh_install = False

                if fresh_install:
                    logger.info("Fresh schema created by Base.metadata.create_all → stamping head.")
                    alembic_command.stamp(cfg, "head")
                else:
                    logger.info("Legacy DB without alembic_version → stamping baseline + upgrading.")
                    alembic_command.stamp(cfg, BASELINE_REVISION)
        alembic_command.upgrade(cfg, "head")
    finally:
        sync_engine.dispose()


async def init_db() -> None:
    """Create tables (for fresh installs) and apply Alembic migrations."""
    logger.info("Initialising database tables …")

    async with engine.begin() as conn:
        # create_all is idempotent — keeps fresh installs simple; Alembic still owns migrations
        await conn.run_sync(Base.metadata.create_all)

        dialect = conn.dialect.name
        if dialect == "sqlite":
            # Alembic supports SQLite poorly with ALTER semantics; we rely on create_all here
            # and skip Alembic for the sqlite test path.
            cols = await conn.execute(text("PRAGMA table_info('fs_tasks')"))
            col_names = {str(row[1]) for row in cols.fetchall()}
            if "status" not in col_names:
                await conn.execute(
                    text("ALTER TABLE fs_tasks ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'PENDING'")
                )
            doc_cols = await conn.execute(text("PRAGMA table_info('fs_documents')"))
            doc_col_names = {str(row[1]) for row in doc_cols.fetchall()}
            if "project_id" not in doc_col_names:
                await conn.execute(text("ALTER TABLE fs_documents ADD COLUMN project_id TEXT"))
            if "order_in_project" not in doc_col_names:
                await conn.execute(text("ALTER TABLE fs_documents ADD COLUMN order_in_project INTEGER DEFAULT 0"))
            logger.info("Database tables ready (sqlite — Alembic skipped).")
            return

        if dialect == "postgresql":
            # Legacy enum add: keep IF NOT EXISTS safety even after Alembic adoption
            new_enum_values = [
                "SECTION_EDITED",
                "SECTION_ADDED",
                "ANALYSIS_CANCELLED",
            ]
            for val in new_enum_values:
                try:
                    await conn.execute(text(f"ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS '{val}'"))
                except Exception as exc:
                    logger.debug("Enum add skipped for %s: %s", val, exc)

    # Alembic runs on a sync engine, in a thread
    try:
        await anyio.to_thread.run_sync(_run_alembic_sync)
    except Exception as exc:
        logger.error("Alembic upgrade failed: %s", exc, exc_info=True)
        raise

    logger.info("Database tables ready.")
