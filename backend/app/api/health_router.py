"""Health check endpoint — verifies DB, Qdrant, and LLM connectivity."""

import logging
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.llm import get_llm_client
from app.models.schemas import APIResponse, HealthResponse, ServiceHealth
from app.vector import get_qdrant_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


async def _check_db(db: AsyncSession) -> ServiceHealth:
    """Check PostgreSQL connectivity."""
    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000
        return ServiceHealth(status="healthy", latency_ms=round(latency, 2))
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        logger.error("DB health check failed: %s", exc)
        return ServiceHealth(
            status="unhealthy",
            latency_ms=round(latency, 2),
            detail=str(exc),
        )


async def _check_qdrant() -> ServiceHealth:
    """Check Qdrant connectivity."""
    start = time.perf_counter()
    try:
        manager = get_qdrant_manager()
        healthy = await manager.check_health()
        latency = (time.perf_counter() - start) * 1000
        return ServiceHealth(
            status="healthy" if healthy else "unhealthy",
            latency_ms=round(latency, 2),
        )
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        logger.error("Qdrant health check failed: %s", exc)
        return ServiceHealth(
            status="unhealthy",
            latency_ms=round(latency, 2),
            detail=str(exc),
        )


async def _check_llm() -> ServiceHealth:
    """Check LLM connectivity (skips if no API key configured)."""
    start = time.perf_counter()
    try:
        from app.config import get_settings
        settings = get_settings()

        # Check the appropriate API key based on provider
        provider = settings.LLM_PROVIDER.lower().strip()
        key_map = {
            "anthropic": settings.ANTHROPIC_API_KEY,
            "openai": settings.OPENAI_API_KEY,
            "groq": getattr(settings, "GROQ_API_KEY", ""),
            "openrouter": getattr(settings, "OPENROUTER_API_KEY", ""),
        }
        key = key_map.get(provider, "")

        if not key or key.startswith("your_"):
            latency = (time.perf_counter() - start) * 1000
            return ServiceHealth(
                status="unconfigured",
                latency_ms=round(latency, 2),
                detail=f"API key not set for provider '{provider}' — LLM calls will fail until configured",
            )

        client = get_llm_client()
        healthy = await client.check_health()
        latency = (time.perf_counter() - start) * 1000
        return ServiceHealth(
            status="healthy" if healthy else "unhealthy",
            latency_ms=round(latency, 2),
            detail=f"provider={provider}, model={settings.PRIMARY_MODEL}",
        )
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        logger.error("LLM health check failed: %s", exc)
        return ServiceHealth(
            status="unhealthy",
            latency_ms=round(latency, 2),
            detail=str(exc),
        )


@router.get("/health", response_model=APIResponse[HealthResponse])
async def health_check(
    db: AsyncSession = Depends(get_db),
) -> APIResponse[HealthResponse]:
    """System health check — verifies all service connections."""
    db_health = await _check_db(db)
    qdrant_health = await _check_qdrant()
    llm_health = await _check_llm()

    # Overall status
    statuses = [db_health.status, qdrant_health.status]
    if all(s == "healthy" for s in statuses):
        overall = "healthy"
    elif any(s == "unhealthy" for s in statuses):
        overall = "unhealthy"
    else:
        overall = "degraded"

    # LLM being unconfigured doesn't make the system unhealthy
    # (L1 doesn't use LLM calls yet)
    if llm_health.status == "unconfigured" and overall == "healthy":
        overall = "healthy"

    return APIResponse(
        data=HealthResponse(
            status=overall,
            db=db_health,
            qdrant=qdrant_health,
            llm=llm_health,
        ),
    )
