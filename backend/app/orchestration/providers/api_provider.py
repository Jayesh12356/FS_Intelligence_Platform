"""API Provider — wraps the existing direct LLM API calls (Phase 1 behavior)."""

from typing import Any

from app.orchestration.base import BuildResult, ExecutionProvider


class APIProvider(ExecutionProvider):
    """Routes LLM calls through the existing multi-provider LLM client (direct API)."""

    name = "api"
    display_name = "Direct API (OpenAI / Anthropic / Groq / OpenRouter)"
    capabilities = ["llm"]
    llm_selectable = True

    async def call_llm(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        from app.llm import get_llm_client
        client = get_llm_client()
        return await client.call_llm(
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            role=kwargs.get("role", "primary"),
        )

    async def build_task(self, task_context: dict, output_folder: str, **kwargs: Any) -> BuildResult:
        raise NotImplementedError("API provider does not support build tasks")

    async def check_health(self) -> bool:
        try:
            from app.llm import get_llm_client
            client = get_llm_client()
            return await client.check_health()
        except Exception:
            return False
