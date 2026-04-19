"""One-shot reset: truncates all DB tables, clears Qdrant, deletes uploads.

Usage:
    cd backend && python -m scripts.reset_all
"""

import asyncio
import logging
import shutil
import sys
from pathlib import Path

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.config import get_settings
from app.db.base import engine
from app.vector.client import COLLECTIONS, QdrantManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("reset_all")

TABLES_TO_TRUNCATE = [
    "mcp_session_events",
    "mcp_sessions",
    "build_snapshots",
    "file_registry",
    "build_states",
    "pipeline_cache",
    "test_cases",
    "audit_events",
    "rework_estimates",
    "task_impacts",
    "fs_changes",
    "duplicate_flags",
    "fs_approvals",
    "fs_mentions",
    "fs_comments",
    "debate_results",
    "traceability_entries",
    "fs_tasks",
    "compliance_tags",
    "edge_case_gaps",
    "contradictions",
    "ambiguity_flags",
    "analysis_results",
    "fs_versions",
    "code_uploads",
    "fs_documents",
    "fs_projects",
]


async def reset_database() -> None:
    logger.info("Resetting database tables...")
    async with engine.begin() as conn:
        dialect = conn.dialect.name
        for table in TABLES_TO_TRUNCATE:
            try:
                if dialect == "postgresql":
                    await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                else:
                    await conn.execute(text(f"DELETE FROM {table}"))
                logger.info("  Cleared table: %s", table)
            except Exception as exc:
                logger.warning("  Skip table %s: %s", table, exc)
    logger.info("Database reset complete.")


def reset_qdrant() -> None:
    logger.info("Resetting Qdrant collections...")
    try:
        qdrant = QdrantManager()
        for name, config in COLLECTIONS.items():
            try:
                qdrant.client.delete_collection(collection_name=name)
                logger.info("  Deleted collection: %s", name)
            except Exception:
                logger.info("  Collection %s did not exist", name)
            from qdrant_client.http import models as qdrant_models

            qdrant.client.create_collection(
                collection_name=name,
                vectors_config=qdrant_models.VectorParams(
                    size=config["size"],
                    distance=config["distance"],
                ),
            )
            logger.info("  Recreated collection: %s (dim=%d)", name, config["size"])
        logger.info("Qdrant reset complete.")
    except Exception as exc:
        logger.warning("Qdrant reset skipped (not reachable): %s", exc)


def reset_uploads() -> None:
    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR)
    if upload_dir.exists():
        shutil.rmtree(upload_dir)
        logger.info("Deleted uploads directory: %s", upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Recreated empty uploads directory: %s", upload_dir)


def reset_logs() -> None:
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    if log_dir.exists():
        shutil.rmtree(log_dir)
        logger.info("Deleted logs directory: %s", log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
    else:
        logger.info("No logs directory to clean.")


async def main() -> None:
    logger.info("=" * 60)
    logger.info("FS Intelligence Platform — Full Reset")
    logger.info("=" * 60)

    await reset_database()
    reset_qdrant()
    reset_uploads()
    reset_logs()

    logger.info("=" * 60)
    logger.info("All data cleared. Fresh start ready!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
