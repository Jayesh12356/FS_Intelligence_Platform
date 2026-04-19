"""Orchestration API — tool configuration, health checks, and provider management."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import clear_settings_cache
from app.db.base import get_db
from app.db.models import ToolConfigDB
from app.models.schemas import APIResponse
from app.orchestration import get_tool_registry
from app.orchestration.config_resolver import invalidate_orchestration_config_cache

logger = logging.getLogger(__name__)

# All three providers are valid Document LLMs. ``cursor`` is served via
# the paste-per-action flow (see ``app.api.cursor_task_router``): the
# UI shows a ready-to-paste prompt, and Cursor submits the result via
# the MCP submit tools. ``api`` and ``claude_code`` are synchronous.
ALLOWED_LLM_PROVIDERS = frozenset({"api", "claude_code", "cursor"})

# Direct API cannot write multi-file code, so api is not allowed as a
# build provider. Only the real agentic providers are.
ALLOWED_BUILD_PROVIDERS = frozenset({"cursor", "claude_code"})

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


class ProviderInfo(BaseModel):
    name: str
    display_name: str
    capabilities: list[str]
    healthy: bool | None = None
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
    llm_provider: str | None = None
    build_provider: str | None = None
    frontend_provider: str | None = None
    fallback_chain: list[str] | None = None
    cursor_config: dict | None = None
    claude_code_config: dict | None = None


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
    result = await db.execute(select(ToolConfigDB).where(ToolConfigDB.user_id == "default").limit(1))
    config = result.scalar_one_or_none()

    if not config:
        config = ToolConfigDB(id=uuid.uuid4(), user_id="default")
        db.add(config)
        await db.commit()
        await db.refresh(config)

    # Auto-migrate legacy rows that hold an unknown provider id.
    migrated = False
    if config.llm_provider not in ALLOWED_LLM_PROVIDERS:
        logger.warning(
            "Migrating stale llm_provider=%r to 'api'",
            config.llm_provider,
        )
        config.llm_provider = "api"
        migrated = True
    if config.build_provider not in ALLOWED_BUILD_PROVIDERS:
        logger.warning(
            "Migrating stale build_provider=%r to 'cursor'",
            config.build_provider,
        )
        config.build_provider = "cursor"
        migrated = True
    cleaned_chain = [p for p in (config.fallback_chain or []) if p in ALLOWED_LLM_PROVIDERS]
    if cleaned_chain != (config.fallback_chain or []):
        config.fallback_chain = cleaned_chain or ["api"]
        migrated = True
    if migrated:
        await db.commit()
        await db.refresh(config)
        invalidate_orchestration_config_cache()

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
    result = await db.execute(select(ToolConfigDB).where(ToolConfigDB.user_id == "default").limit(1))
    config = result.scalar_one_or_none()

    if not config:
        config = ToolConfigDB(id=uuid.uuid4(), user_id="default")
        db.add(config)

    if update.llm_provider is not None and update.llm_provider not in ALLOWED_LLM_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=(f"llm_provider must be one of: {sorted(ALLOWED_LLM_PROVIDERS)}."),
        )
    if update.build_provider is not None and update.build_provider not in ALLOWED_BUILD_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"build_provider must be one of: {sorted(ALLOWED_BUILD_PROVIDERS)}. Direct API cannot perform builds."
            ),
        )

    # Sanitise fallback chain: if cursor leaked in from an older config
    # it must be stripped now that Cursor is build-only.
    if update.fallback_chain is not None:
        update.fallback_chain = [p for p in update.fallback_chain if p in ALLOWED_LLM_PROVIDERS] or ["api"]

    for field_name in [
        "llm_provider",
        "build_provider",
        "frontend_provider",
        "fallback_chain",
        "cursor_config",
        "claude_code_config",
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


@router.get("/mcp-config", response_model=APIResponse[dict])
async def get_mcp_config(
    document_id: str | None = None,
    stack: str = "Next.js + FastAPI",
    output_folder: str = "./output",
) -> APIResponse[dict]:
    """Canonical MCP JSON snippets for Cursor and Claude Code.

    A single source of truth so the in-app Build page, the docs, and the
    files checked into the repo never drift. Both snippets launch the same
    ``mcp-server/server.py`` entry point against the backend URL specified
    by settings (``BACKEND_SELF_URL``), so users can copy/paste verbatim.

    When ``document_id`` is supplied, the agent prompt and CLI command are
    rendered with the real document id, stack, and output folder, so the
    Build page can show a one-click copyable kickoff string. ``auto_proceed``
    is always ``true`` to match the in-app build CTA semantics
    (``GET /api/fs/{doc_id}/build-prompt``).
    """
    from app.config import get_settings

    settings = get_settings()
    backend_url = getattr(settings, "BACKEND_SELF_URL", None) or "http://localhost:8000"

    cursor_snippet = {
        "mcpServers": {
            "fs-intelligence-platform": {
                "command": "python",
                "args": ["mcp-server/server.py"],
                "env": {"BACKEND_URL": backend_url},
            }
        }
    }

    claude_snippet = {
        "mcpServers": {
            "fs-intelligence-platform": {
                "command": "python",
                "args": ["mcp-server/server.py"],
                "env": {"BACKEND_URL": backend_url},
            }
        }
    }

    doc_token = document_id or "<document_id>"
    agent_prompt = (
        f"Use the start_build_loop prompt for document {doc_token} "
        f"with stack='{stack}', output_folder='{output_folder}', "
        f"auto_proceed='true'."
    )
    cli_command = f'claude --mcp-config mcp-config.json -p "{agent_prompt}"'

    return APIResponse(
        data={
            "cursor": {
                "path": ".cursor/mcp.json",
                "snippet": cursor_snippet,
                "agent_prompt": agent_prompt,
                "install_steps": [
                    "Install Cursor (Pro or Business for MCP + Agent).",
                    "Create .cursor/mcp.json at the repository root with the snippet below.",
                    "Open the MCP panel in Cursor and confirm fs-intelligence-platform shows as connected.",
                    "In Agent mode, paste the one-line agent_prompt below.",
                ],
            },
            "claude_code": {
                "path": "mcp-config.json",
                "snippet": claude_snippet,
                "agent_prompt": agent_prompt,
                "cli_command": cli_command,
                "install_steps": [
                    "npm install -g @anthropic-ai/claude-code",
                    "claude login  # one-time browser auth",
                    "Create mcp-config.json at the repository root with the snippet below.",
                    "Run the CLI command below; Claude Code will drive the full build loop via MCP tools.",
                ],
            },
            "document_id": document_id,
            "stack": stack,
            "output_folder": output_folder,
            "notes": (
                "Both snippets target the same MCP server and backend. "
                "BACKEND_URL is driven by the BACKEND_SELF_URL setting so "
                "production deployments can override it."
            ),
        }
    )
