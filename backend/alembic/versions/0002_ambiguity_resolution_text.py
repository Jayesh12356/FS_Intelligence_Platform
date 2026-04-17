"""ambiguity resolution_text + resolved_at

Revision ID: 0002_ambiguity_resolution_text
Revises: 0001_baseline
Create Date: 2026-04-17
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_ambiguity_resolution_text"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ambiguity_flags") as batch:
        batch.add_column(sa.Column("resolution_text", sa.Text(), nullable=True))
        batch.add_column(sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ambiguity_flags") as batch:
        batch.drop_column("resolved_at")
        batch.drop_column("resolution_text")
