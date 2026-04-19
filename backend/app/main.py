"""FS Intelligence Platform — FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.init_db import init_db
from app.errors import install_exception_handlers
from app.middleware import RequestContextMiddleware, RequestIdLogFilter
from app.vector import get_qdrant_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-8s | rid=%(request_id)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
for _h in logging.getLogger().handlers:
    _h.addFilter(RequestIdLogFilter())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("🚀 Starting FS Intelligence Platform …")
    settings = get_settings()
    # Do not log DB host/credentials; scheme only
    db_scheme = settings.DATABASE_URL.split("://", 1)[0]
    logger.info("Database: %s://<redacted>", db_scheme)
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

    # Start the Cursor-task TTL sweeper (expires abandoned paste-per-
    # action tasks). Best-effort: failure here must not stop startup.
    sweeper_task = None
    try:
        from app.api.cursor_task_router import _sweeper_loop as _cursor_task_sweeper

        sweeper_task = asyncio.create_task(_cursor_task_sweeper())
        logger.info("Cursor task TTL sweeper started")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cursor task sweeper did not start: %s", exc)

    # Idempotent ANALYZED back-fill — for documents that completed
    # analysis BEFORE the lifecycle telemetry uplift shipped, their
    # activity log only shows UPLOADED. We add a single ANALYZED event
    # per such document so the per-doc Lifecycle strip and the global
    # /monitoring activity feed correctly show "Analysis completed"
    # without operators having to re-run the pipeline.
    try:
        from app.startup.backfill import backfill_analyzed_events

        await backfill_analyzed_events()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ANALYZED back-fill skipped: %s", exc)

    logger.info("✅ All services initialised")
    yield
    logger.info("👋 Shutting down FS Intelligence Platform")
    if sweeper_task is not None:
        sweeper_task.cancel()
        try:
            await sweeper_task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(
    title="FS Intelligence Platform",
    description="AI-powered platform that transforms Functional Specification documents into dev-ready task breakdowns.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Middleware + error handlers ───────────────────────
settings = get_settings()
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
install_exception_handlers(app)

# ── Routers ────────────────────────────────────────────
# New feature routers
from app.api.activity_router import router as activity_router  # noqa: E402
from app.api.analysis_router import router as analysis_router  # noqa: E402
from app.api.approval_router import router as approval_router  # noqa: E402
from app.api.audit_router import router as audit_router  # noqa: E402
from app.api.build_router import router as build_router  # noqa: E402
from app.api.code_router import router as code_router  # noqa: E402
from app.api.collab_router import router as collab_router  # noqa: E402

# Cursor paste-per-action tasks
from app.api.cursor_task_router import router as cursor_task_router  # noqa: E402

# L9 routers
from app.api.duplicate_router import router as duplicate_router  # noqa: E402

# L10 routers
from app.api.export_router import router as export_router  # noqa: E402
from app.api.fs_router import router as fs_router  # noqa: E402
from app.api.health_router import router as health_router  # noqa: E402

# Phase 2 routers
from app.api.idea_router import router as idea_router  # noqa: E402
from app.api.impact_router import router as impact_router  # noqa: E402
from app.api.library_router import router as library_router  # noqa: E402
from app.api.mcp_router import router as mcp_router  # noqa: E402
from app.api.orchestration_router import router as orchestration_router  # noqa: E402
from app.api.project_router import router as project_router  # noqa: E402
from app.api.tasks_router import router as tasks_router  # noqa: E402

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
app.include_router(build_router)
# New features
app.include_router(activity_router)
app.include_router(project_router)
# Phase 2
app.include_router(idea_router)
app.include_router(orchestration_router)
# Cursor paste-per-action tasks
app.include_router(cursor_task_router)


@app.get("/")
async def root():
    """Root endpoint — API info."""
    return {
        "name": "FS Intelligence Platform",
        "version": "0.1.0",
        "docs": "/docs",
    }
