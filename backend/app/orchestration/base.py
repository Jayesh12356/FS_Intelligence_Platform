"""Abstract base for execution providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class BuildResult:
    """Result from a build task execution."""
    success: bool
    files_created: list[str] = field(default_factory=list)
    output: str = ""
    error: Optional[str] = None


class ExecutionProvider(ABC):
    """Base class for all tool providers.

    Each provider declares which capabilities it supports and implements
    the corresponding methods. Unsupported capabilities raise NotImplementedError.
    """

    name: str = "base"
    display_name: str = "Base Provider"
    capabilities: list[str] = []
    # Shown in Settings as an option for automatic (server-side) LLM routing.
    llm_selectable: bool = True
    # Extra context for Monitoring / docs (e.g. MCP build vs CLI).
    health_note: str = ""

    @abstractmethod
    async def call_llm(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        """Route an LLM call through this provider."""

    @abstractmethod
    async def build_task(
        self,
        task_context: dict,
        output_folder: str,
        **kwargs: Any,
    ) -> BuildResult:
        """Execute a build task through this provider."""

    @abstractmethod
    async def check_health(self) -> bool:
        """Check if this provider is available and configured."""

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities
