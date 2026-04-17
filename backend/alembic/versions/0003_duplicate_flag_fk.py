"""FK on duplicate_flags.similar_fs_id

Revision ID: 0003_duplicate_flag_fk
Revises: 0002_ambiguity_resolution_text
Create Date: 2026-04-17
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003_duplicate_flag_fk"
down_revision: Union[str, None] = "0002_ambiguity_resolution_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_NAME = "duplicate_flags_similar_fs_id_fkey"


def upgrade() -> None:
    # Drop any stale rows whose target document was already deleted so the
    # constraint creation succeeds.
    op.execute(
        "DELETE FROM duplicate_flags "
        "WHERE similar_fs_id NOT IN (SELECT id FROM fs_documents)"
    )
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.create_foreign_key(
            _FK_NAME,
            "duplicate_flags",
            "fs_documents",
            ["similar_fs_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.drop_constraint(_FK_NAME, "duplicate_flags", type_="foreignkey")
