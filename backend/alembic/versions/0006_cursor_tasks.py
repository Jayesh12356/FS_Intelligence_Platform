"""Drop worker-loop tables (llm_request_queue, llm_workers) and add cursor_tasks.

Revision ID: 0006_cursor_tasks
Revises: 0005_llm_request_queue
Create Date: 2026-04-17

0.4.0 switches Cursor from a long-running worker loop to a per-action
paste flow. The queue-bridge tables are dropped and a single
``cursor_tasks`` table replaces them. Every Generate FS / Analyze /
Reverse FS click mints one row; Cursor submits the result via MCP.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0006_cursor_tasks"
down_revision = "0005_llm_request_queue"
branch_labels = None
depends_on = None


def _kind_type(bind):
    if bind.dialect.name == "postgresql":
        return PG_ENUM(
            "GENERATE_FS",
            "ANALYZE",
            "REVERSE_FS",
            name="cursor_task_kind",
            create_type=False,
        )
    return sa.Enum(
        "GENERATE_FS",
        "ANALYZE",
        "REVERSE_FS",
        name="cursor_task_kind",
    )


def _status_type(bind):
    if bind.dialect.name == "postgresql":
        return PG_ENUM(
            "PENDING",
            "CLAIMED",
            "DONE",
            "FAILED",
            "EXPIRED",
            name="cursor_task_status",
            create_type=False,
        )
    return sa.Enum(
        "PENDING",
        "CLAIMED",
        "DONE",
        "FAILED",
        "EXPIRED",
        name="cursor_task_status",
    )


def _table_exists(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    # Drop the old worker-loop tables if present.
    if _table_exists(bind, "llm_workers"):
        try:
            op.drop_index("ix_llm_workers_heartbeat", table_name="llm_workers")
        except Exception:
            pass
        op.drop_table("llm_workers")
    if _table_exists(bind, "llm_request_queue"):
        try:
            op.drop_index("ix_llm_queue_status_created", table_name="llm_request_queue")
        except Exception:
            pass
        op.drop_table("llm_request_queue")
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("DROP TYPE IF EXISTS llm_request_status")
        bind.exec_driver_sql("DROP TYPE IF EXISTS llm_bundle_kind")

    # Create cursor_tasks.
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("""
DO $$ BEGIN
    CREATE TYPE cursor_task_kind AS ENUM ('GENERATE_FS', 'ANALYZE', 'REVERSE_FS');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
""")
        bind.exec_driver_sql("""
DO $$ BEGIN
    CREATE TYPE cursor_task_status AS ENUM ('PENDING', 'CLAIMED', 'DONE', 'FAILED', 'EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
""")
    else:
        _kind_type(bind).create(bind, checkfirst=True)
        _status_type(bind).create(bind, checkfirst=True)

    if not _table_exists(bind, "cursor_tasks"):
        op.create_table(
            "cursor_tasks",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("kind", _kind_type(bind), nullable=False),
            sa.Column("status", _status_type(bind), nullable=False, server_default="PENDING"),
            sa.Column("related_id", UUID(as_uuid=True), nullable=True),
            sa.Column("input_payload", sa.JSON, nullable=False),
            sa.Column("prompt_text", sa.Text, nullable=False),
            sa.Column("output_payload", sa.JSON, nullable=True),
            sa.Column("result_ref", UUID(as_uuid=True), nullable=True),
            sa.Column("error", sa.Text, nullable=True),
            sa.Column("ttl_sec", sa.Integer, nullable=False, server_default="900"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_cursor_tasks_status_created",
            "cursor_tasks",
            ["status", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "cursor_tasks"):
        try:
            op.drop_index("ix_cursor_tasks_status_created", table_name="cursor_tasks")
        except Exception:
            pass
        op.drop_table("cursor_tasks")
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("DROP TYPE IF EXISTS cursor_task_status")
        bind.exec_driver_sql("DROP TYPE IF EXISTS cursor_task_kind")
