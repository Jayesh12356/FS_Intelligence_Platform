"""Extend ``auditeventtype`` enum with lifecycle / build telemetry values.

Revision ID: 0009_audit_event_type_lifecycle
Revises: 0008_fs_document_analysis_stale
Create Date: 2026-04-18

Adds 11 new values to the ``auditeventtype`` PostgreSQL enum so the
activity log and the per-document Lifecycle timeline can show every
meaningful state change between upload and build:

* ANALYSIS_REFINED, AMBIGUITY_RESOLVED, CONTRADICTION_ACCEPTED,
  EDGE_CASE_ACCEPTED, VERSION_REVERTED
* BUILD_STARTED, BUILD_PHASE_CHANGED, BUILD_TASK_COMPLETED,
  FILE_REGISTERED, BUILD_COMPLETED, BUILD_FAILED

Postgres ``ALTER TYPE ... ADD VALUE`` is non-transactional, so this
migration runs each statement in autocommit. It is idempotent via
``IF NOT EXISTS`` so re-running does not error. SQLite test envs
recreate the schema from ``Base.metadata`` and need no migration.
"""

from __future__ import annotations

from alembic import op

revision = "0009_audit_event_type_lifecycle"
down_revision = "0008_fs_document_analysis_stale"
branch_labels = None
depends_on = None


_NEW_VALUES = (
    "ANALYSIS_REFINED",
    "AMBIGUITY_RESOLVED",
    "CONTRADICTION_ACCEPTED",
    "EDGE_CASE_ACCEPTED",
    "VERSION_REVERTED",
    "BUILD_STARTED",
    "BUILD_PHASE_CHANGED",
    "BUILD_TASK_COMPLETED",
    "FILE_REGISTERED",
    "BUILD_COMPLETED",
    "BUILD_FAILED",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite stores the enum as a plain string column and recreates
        # the schema from ``Base.metadata`` for tests, so no DDL needed.
        return

    # ``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction
    # block in older Postgres versions; use an autocommit connection.
    with op.get_context().autocommit_block():
        for value in _NEW_VALUES:
            op.execute(
                f"ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS '{value}'"
            )


def downgrade() -> None:
    # Postgres has no DROP VALUE for an enum type. Removing the values
    # would require recreating the type and rewriting every audit row,
    # which is destructive. We deliberately make this a no-op.
    pass
