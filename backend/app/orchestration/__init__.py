"""Tool Orchestration Layer — routes LLM/build work through subscription tools."""

from functools import lru_cache

from app.orchestration.registry import ToolRegistry


@lru_cache
def get_tool_registry() -> ToolRegistry:
    """Return a cached ToolRegistry singleton."""
    return ToolRegistry()
