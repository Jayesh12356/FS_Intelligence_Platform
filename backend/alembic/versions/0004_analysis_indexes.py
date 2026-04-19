"""Add indexes on per-document analysis tables.

Revision ID: 0004_analysis_indexes
Revises: 0003_duplicate_flag_fk
Create Date: 2026-04-17
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_analysis_indexes"
down_revision = "0003_duplicate_flag_fk"
branch_labels = None
depends_on = None


_INDEXES = [
    ("ix_ambiguity_flags_fs_id", "ambiguity_flags", "fs_id"),
    ("ix_fs_tasks_fs_id", "fs_tasks", "fs_id"),
    ("ix_analysis_results_fs_id", "analysis_results", "fs_id"),
    ("ix_contradictions_fs_id", "contradictions", "fs_id"),
    ("ix_edge_cases_fs_id", "edge_cases", "fs_id"),
    ("ix_fs_versions_fs_id", "fs_versions", "fs_id"),
    ("ix_audit_events_fs_id", "audit_events", "fs_id"),
    ("ix_duplicate_flags_fs_id", "duplicate_flags", "fs_id"),
    ("ix_test_cases_fs_id", "test_cases", "fs_id"),
    ("ix_traceability_entries_fs_id", "traceability_entries", "fs_id"),
]


def _table_exists(bind, name: str) -> bool:
    from sqlalchemy import inspect

    return name in inspect(bind).get_table_names()


def _index_exists(bind, table: str, name: str) -> bool:
    from sqlalchemy import inspect

    try:
        existing = {ix["name"] for ix in inspect(bind).get_indexes(table)}
    except Exception:
        return False
    return name in existing


def upgrade() -> None:
    bind = op.get_bind()
    for index_name, table, column in _INDEXES:
        if not _table_exists(bind, table):
            continue
        if _index_exists(bind, table, index_name):
            continue
        op.create_index(index_name, table, [column])


def downgrade() -> None:
    bind = op.get_bind()
    for index_name, table, _ in _INDEXES:
        if not _table_exists(bind, table):
            continue
        if _index_exists(bind, table, index_name):
            op.drop_index(index_name, table_name=table)
