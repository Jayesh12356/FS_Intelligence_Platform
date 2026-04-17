"""baseline — matches current Base.metadata after ad-hoc migrations

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-17

The baseline is a no-op. The startup hook creates missing tables from
``Base.metadata`` and then stamps this revision so subsequent Alembic
migrations run forward from here.
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
