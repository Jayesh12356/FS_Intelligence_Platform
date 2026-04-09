"""FS Intelligence Platform — FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.init_db import init_db
from app.vector import get_qdrant_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("🚀 Starting FS Intelligence Platform …")
    settings = get_settings()
    logger.info("Database: %s", settings.DATABASE_URL.split("@")[-1])
    logger.info("Qdrant:   %s", settings.QDRANT_URL)
    logger.info("LLM:      %s / %s", settings.LLM_PROVIDER, settings.PRIMARY_MODEL)

    # Initialise database tables
    await init_db()

    # Initialise Qdrant collections (with retry — Qdrant may still be starting)
    qdrant = get_qdrant_manager()
    max_retries = 10
    for attempt in range(1, max_retries + 1):
        try:
            await qdrant.create_collections()
            break
        except Exception as exc:
            if attempt == max_retries:
                logger.error("Qdrant init failed after %d attempts: %s", max_retries, exc)
                raise
            logger.warning("Qdrant not ready (attempt %d/%d): %s — retrying in 3s …", attempt, max_retries, exc)
            await asyncio.sleep(3)

    logger.info("✅ All services initialised")
    yield
    logger.info("👋 Shutting down FS Intelligence Platform")


app = FastAPI(
    title="FS Intelligence Platform",
    description="AI-powered platform that transforms Functional Specification documents into dev-ready task breakdowns.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────
from app.api.fs_router import router as fs_router  # noqa: E402
from app.api.health_router import router as health_router  # noqa: E402
from app.api.analysis_router import router as analysis_router  # noqa: E402
from app.api.tasks_router import router as tasks_router  # noqa: E402
from app.api.impact_router import router as impact_router  # noqa: E402
from app.api.code_router import router as code_router  # noqa: E402
# L9 routers
from app.api.duplicate_router import router as duplicate_router  # noqa: E402
from app.api.library_router import router as library_router  # noqa: E402
from app.api.collab_router import router as collab_router  # noqa: E402
from app.api.approval_router import router as approval_router  # noqa: E402
from app.api.audit_router import router as audit_router  # noqa: E402
# L10 routers
from app.api.export_router import router as export_router  # noqa: E402
from app.api.mcp_router import router as mcp_router  # noqa: E402

app.include_router(fs_router)
app.include_router(health_router)
app.include_router(analysis_router)
app.include_router(tasks_router)
app.include_router(impact_router)
app.include_router(code_router)
# L9
app.include_router(duplicate_router)
app.include_router(library_router)
app.include_router(collab_router)
app.include_router(approval_router)
app.include_router(audit_router)
# L10
app.include_router(export_router)
app.include_router(mcp_router)


@app.get("/")
async def root():
    """Root endpoint — API info."""
    return {
        "name": "FS Intelligence Platform",
        "version": "0.1.0",
        "docs": "/docs",
    }
