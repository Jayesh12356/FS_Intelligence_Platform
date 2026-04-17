"""Orchestration API — tool configuration, health checks, and provider management."""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import ToolConfigDB
from app.models.schemas import APIResponse
from app.orchestration import get_tool_registry
from app.config import clear_settings_cache
from app.orchestration.config_resolver import invalidate_orchestration_config_cache

logger = logging.getLogger(__name__)

ALLOWED_LLM_PROVIDERS = frozenset({"api", "claude_code", "cursor"})

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


class ProviderInfo(BaseModel):
    name: str
    display_name: str
    capabilities: list[str]
    healthy: Optional[bool] = None
    llm_selectable: bool = True
    health_note: str = ""


class ToolConfigResponse(BaseModel):
    id: str
    llm_provider: str
    build_provider: str
    frontend_provider: str
    fallback_chain: list[str]
    cursor_config: dict
    claude_code_config: dict


class ToolConfigUpdate(BaseModel):
    llm_provider: Optional[str] = None
    build_provider: Optional[str] = None
    frontend_provider: Optional[str] = None
    fallback_chain: Optional[list[str]] = None
    cursor_config: Optional[dict] = None
    claude_code_config: Optional[dict] = None


@router.get("/providers", response_model=APIResponse[list[ProviderInfo]])
async def list_providers() -> APIResponse[list[ProviderInfo]]:
    """List all available providers with their capabilities."""
    registry = get_tool_registry()
    providers_data = registry.list_providers()
    health = await registry.health_check_all()

    result = [
        ProviderInfo(
            name=p["name"],
            display_name=p["display_name"],
            capabilities=p["capabilities"],
            healthy=health.get(p["name"]),
            llm_selectable=p.get("llm_selectable", True),
            health_note=p.get("health_note") or "",
        )
        for p in providers_data
    ]
    return APIResponse(data=result)


@router.get("/config", response_model=APIResponse[ToolConfigResponse])
async def get_config(db: AsyncSession = Depends(get_db)) -> APIResponse[ToolConfigResponse]:
    """Get the current tool orchestration configuration."""
    result = await db.execute(
        select(ToolConfigDB).where(ToolConfigDB.user_id == "default").limit(1)
    )
    config = result.scalar_one_or_none()

    if not config:
        config = ToolConfigDB(id=uuid.uuid4(), user_id="default")
        db.add(config)
        await db.commit()
        await db.refresh(config)

    return APIResponse(
        data=ToolConfigResponse(
            id=str(config.id),
            llm_provider=config.llm_provider,
            build_provider=config.build_provider,
            frontend_provider=config.frontend_provider,
            fallback_chain=config.fallback_chain or ["api"],
            cursor_config=config.cursor_config or {},
            claude_code_config=config.claude_code_config or {},
        )
    )


@router.put("/config", response_model=APIResponse[ToolConfigResponse])
async def update_config(
    update: ToolConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ToolConfigResponse]:
    """Update tool orchestration configuration."""
    result = await db.execute(
        select(ToolConfigDB).where(ToolConfigDB.user_id == "default").limit(1)
    )
    config = result.scalar_one_or_none()

    if not config:
        config = ToolConfigDB(id=uuid.uuid4(), user_id="default")
        db.add(config)

    if update.llm_provider is not None and update.llm_provider not in ALLOWED_LLM_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"llm_provider must be one of: {sorted(ALLOWED_LLM_PROVIDERS)}",
        )

    for field_name in [
        "llm_provider", "build_provider", "frontend_provider", "fallback_chain",
        "cursor_config", "claude_code_config",
    ]:
        value = getattr(update, field_name, None)
        if value is not None:
            setattr(config, field_name, value)

    await db.commit()
    await db.refresh(config)
    invalidate_orchestration_config_cache()
    clear_settings_cache()

    return APIResponse(
        data=ToolConfigResponse(
            id=str(config.id),
            llm_provider=config.llm_provider,
            build_provider=config.build_provider,
            frontend_provider=config.frontend_provider,
            fallback_chain=config.fallback_chain or ["api"],
            cursor_config=config.cursor_config or {},
            claude_code_config=config.claude_code_config or {},
        )
    )


@router.post("/test/{provider_name}", response_model=APIResponse[dict])
async def test_provider(provider_name: str) -> APIResponse[dict]:
    """Test a specific provider's health and connectivity."""
    registry = get_tool_registry()
    provider = registry.get(provider_name)

    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    try:
        healthy = await provider.check_health()
        return APIResponse(
            data={
                "provider": provider_name,
                "display_name": provider.display_name,
                "healthy": healthy,
                "capabilities": provider.capabilities,
            }
        )
    except Exception as exc:
        return APIResponse(
            data={
                "provider": provider_name,
                "healthy": False,
                "error": str(exc),
            }
        )


@router.get("/capabilities", response_model=APIResponse[dict])
async def get_capabilities() -> APIResponse[dict]:
    """Map each capability to its available providers."""
    registry = get_tool_registry()
    providers_data = registry.list_providers()

    cap_map: dict[str, list[str]] = {}
    for p in providers_data:
        for cap in p["capabilities"]:
            cap_map.setdefault(cap, []).append(p["name"])

    return APIResponse(data=cap_map)
