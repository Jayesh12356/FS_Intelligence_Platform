"""Database initialisation — creates all tables on startup."""

import logging

from sqlalchemy import text

from app.db.base import Base, engine

# Import models so they register with Base.metadata
from app.db import models  # noqa: F401

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Create all tables if they don't exist."""
    logger.info("Initialising database tables …")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        dialect = conn.dialect.name
        if dialect == "postgresql":
            new_enum_values = [
                "SECTION_EDITED", "SECTION_ADDED", "ANALYSIS_CANCELLED",
            ]
            for val in new_enum_values:
                try:
                    await conn.execute(text(
                        f"ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS '{val}'"
                    ))
                except Exception:
                    pass

            migrations = [
                "ALTER TABLE fs_tasks ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'PENDING'",
                "ALTER TABLE fs_documents ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES fs_projects(id) ON DELETE SET NULL",
                "ALTER TABLE fs_documents ADD COLUMN IF NOT EXISTS order_in_project INTEGER NOT NULL DEFAULT 0",
            ]
            for sql in migrations:
                try:
                    await conn.execute(text(sql))
                except Exception as exc:
                    logger.debug("Migration skip (likely already applied): %s", exc)
        elif dialect == "sqlite":
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
    logger.info("Database tables ready.")
