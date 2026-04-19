"""One-shot probe: assert the auto-heal predicate would fire for
``970889b8-77d4-410c-8012-ae0d516be8b3``.

Usage::

    python -m scripts._probe_970889b8
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB = "postgresql+asyncpg://fsp_user:fsp_secret@localhost:5434/fsplatform"
DOC_ID = "970889b8-77d4-410c-8012-ae0d516be8b3"


async def main() -> None:
    engine = create_async_engine(DB)
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT status::text, analysis_stale, filename "
                    "FROM fs_documents WHERE id = :id"
                ),
                {"id": DOC_ID},
            )
        ).first()
        print(f"doc        : {row}")
        for tbl in (
            "fs_tasks",
            "ambiguity_flags",
            "contradictions",
            "edge_case_gaps",
        ):
            n = (
                await conn.execute(
                    text(f"SELECT count(*) FROM {tbl} WHERE fs_id = :id"),
                    {"id": DOC_ID},
                )
            ).scalar()
            print(f"{tbl:<18}: {n}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
