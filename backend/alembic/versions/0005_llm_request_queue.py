"""Add llm_request_queue and llm_workers tables for the Cursor-IDE bridge.

Revision ID: 0005_llm_request_queue
Revises: 0004_analysis_indexes
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0005_llm_request_queue"
down_revision = "0004_analysis_indexes"
branch_labels = None
depends_on = None


def _kind_type(bind):
    if bind.dialect.name == "postgresql":
        return PG_ENUM(
            "GENERATE_FS",
            "ANALYZE",
            "REVERSE_FS",
            "IMPACT",
            "REFINE",
            "RAW",
            name="llm_bundle_kind",
            create_type=False,
        )
    return sa.Enum(
        "GENERATE_FS",
        "ANALYZE",
        "REVERSE_FS",
        "IMPACT",
        "REFINE",
        "RAW",
        name="llm_bundle_kind",
    )


def _status_type(bind):
    if bind.dialect.name == "postgresql":
        return PG_ENUM(
            "PENDING",
            "CLAIMED",
            "DONE",
            "FAILED",
            "EXPIRED",
            name="llm_request_status",
            create_type=False,
        )
    return sa.Enum(
        "PENDING",
        "CLAIMED",
        "DONE",
        "FAILED",
        "EXPIRED",
        name="llm_request_status",
    )


def _table_exists(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    # PostgreSQL: CREATE TYPE IF NOT EXISTS isn't supported; use DO blocks.
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("""
DO $$ BEGIN
    CREATE TYPE llm_bundle_kind AS ENUM ('GENERATE_FS', 'ANALYZE', 'REVERSE_FS', 'IMPACT', 'REFINE', 'RAW');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
""")
        bind.exec_driver_sql("""
DO $$ BEGIN
    CREATE TYPE llm_request_status AS ENUM ('PENDING', 'CLAIMED', 'DONE', 'FAILED', 'EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
""")
    else:
        _kind_type(bind).create(bind, checkfirst=True)
        _status_type(bind).create(bind, checkfirst=True)

    kind_col = _kind_type(bind)
    status_col = _status_type(bind)

    if not _table_exists(bind, "llm_request_queue"):
        op.create_table(
            "llm_request_queue",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("kind", kind_col, nullable=False, server_default="RAW"),
            sa.Column("role", sa.String(64), nullable=False, server_default="primary"),
            sa.Column("system", sa.Text, nullable=False, server_default=""),
            sa.Column("prompt", sa.Text, nullable=False),
            sa.Column("max_tokens", sa.Integer, nullable=False, server_default="4096"),
            sa.Column("temperature", sa.Float, nullable=False, server_default="0"),
            sa.Column("response_format", sa.String(32), nullable=False, server_default="text"),
            sa.Column("context_json", sa.JSON, nullable=True),
            sa.Column("status", status_col, nullable=False, server_default="PENDING"),
            sa.Column("response_text", sa.Text, nullable=True),
            sa.Column("error", sa.Text, nullable=True),
            sa.Column("worker_id", sa.String(128), nullable=True),
            sa.Column("ttl_sec", sa.Integer, nullable=False, server_default="300"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_llm_queue_status_created", "llm_request_queue", ["status", "created_at"])

    if not _table_exists(bind, "llm_workers"):
        op.create_table(
            "llm_workers",
            sa.Column("id", sa.String(128), primary_key=True),
            sa.Column("session_id", UUID(as_uuid=True), nullable=True),
            sa.Column("client_label", sa.String(128), nullable=False, server_default="cursor-ide"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("requests_handled", sa.Integer, nullable=False, server_default="0"),
        )
        op.create_index("ix_llm_workers_heartbeat", "llm_workers", ["last_heartbeat_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "llm_workers"):
        op.drop_index("ix_llm_workers_heartbeat", table_name="llm_workers")
        op.drop_table("llm_workers")
    if _table_exists(bind, "llm_request_queue"):
        op.drop_index("ix_llm_queue_status_created", table_name="llm_request_queue")
        op.drop_table("llm_request_queue")
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql("DROP TYPE IF EXISTS llm_request_status")
        bind.exec_driver_sql("DROP TYPE IF EXISTS llm_bundle_kind")
