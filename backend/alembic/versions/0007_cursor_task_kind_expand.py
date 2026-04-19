"""Expand cursor_task_kind enum with REFINE and IMPACT.

Revision ID: 0007_cursor_task_kind_expand
Revises: 0006_cursor_tasks
Create Date: 2026-04-17

0.4.0 extends the paste-per-action flow to the last two unbranched
pipeline routes: ``POST /api/fs/{id}/refine`` and ``POST /api/fs/{id}/version``
(impact). Each now mints a CursorTaskDB when ``llm_provider == 'cursor'``
and the enum must accept the new kinds.
"""

from __future__ import annotations

from alembic import op

revision = "0007_cursor_task_kind_expand"
down_revision = "0006_cursor_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("ALTER TYPE cursor_task_kind ADD VALUE IF NOT EXISTS 'REFINE'")
        bind.exec_driver_sql("ALTER TYPE cursor_task_kind ADD VALUE IF NOT EXISTS 'IMPACT'")
    # For SQLite / test harness we recreate the enum when SQLAlchemy
    # materialises it; no schema change is needed.


def downgrade() -> None:
    # PostgreSQL does not support removing values from an ENUM without
    # recreating the type + rewriting every referencing column. Because
    # every CursorTaskDB row referencing REFINE/IMPACT would also need
    # to be migrated, this downgrade is intentionally a no-op. Users
    # needing to revert should manually drop and recreate the enum.
    pass
