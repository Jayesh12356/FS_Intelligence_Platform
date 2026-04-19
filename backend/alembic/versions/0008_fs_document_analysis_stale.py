"""Add ``analysis_stale`` flag to fs_documents.

Revision ID: 0008_fs_document_analysis_stale
Revises: 0007_cursor_task_kind_expand
Create Date: 2026-04-18

After 0.4.x we stopped demoting ``status`` from COMPLETE -> PARSED on
refine / accept-suggestion / accept-contradiction / accept-edge-case.
Instead the document keeps ``status=COMPLETE`` and we flip
``analysis_stale=True`` so the UI can surface a soft "re-analyze to
refresh metrics" banner without losing the Build CTA. Re-running the
analyze pipeline clears the flag.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_fs_document_analysis_stale"
down_revision = "0007_cursor_task_kind_expand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fs_documents",
        sa.Column(
            "analysis_stale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("fs_documents", "analysis_stale")
