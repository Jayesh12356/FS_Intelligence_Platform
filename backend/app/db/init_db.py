"""Database initialisation — creates all tables on startup."""

import logging

from app.db.base import Base, engine

# Import models so they register with Base.metadata
from app.db import models  # noqa: F401

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Create all tables if they don't exist."""
    logger.info("Initialising database tables …")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready.")
