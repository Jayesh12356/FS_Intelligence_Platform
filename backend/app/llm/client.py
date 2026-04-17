"""Unified LLM client — supports Anthropic, OpenAI, Groq, and OpenRouter.

ALL LLM calls in the platform MUST go through this client.
No other file should import an LLM SDK directly.

Provider routing:
  - anthropic  → Anthropic SDK (native)
  - openai     → OpenAI SDK (native)
  - groq       → OpenAI SDK with base_url=https://api.groq.com/openai/v1
  - openrouter → OpenAI SDK with base_url=https://openrouter.ai/api/v1
"""

import json
import logging
import re
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Provider constants ─────────────────────────────────

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
PROVIDER_GROQ = "groq"
PROVIDER_OPENROUTER = "openrouter"

OPENAI_COMPATIBLE_PROVIDERS = {PROVIDER_OPENAI, PROVIDER_GROQ, PROVIDER_OPENROUTER}

_BASE_URLS = {
    PROVIDER_GROQ: "https://api.groq.com/openai/v1",
    PROVIDER_OPENROUTER: "https://openrouter.ai/api/v1",
}

# ── Default models per provider ────────────────────────

_DEFAULT_MODELS = {
    PROVIDER_ANTHROPIC: "claude-sonnet-4-20250514",
    PROVIDER_OPENAI: "gpt-4o-mini",
    PROVIDER_GROQ: "llama-3.3-70b-versatile",
    PROVIDER_OPENROUTER: "anthropic/claude-sonnet-4-20250514",
}


class LLMError(Exception):
    """Raised when an LLM call fails."""

    def __init__(self, message: str, provider: str = "", model: str = ""):
        self.provider = provider
        self.model = model
        super().__init__(message)


class LLMClient:
    """Unified LLM client supporting Anthropic, OpenAI, Groq, and OpenRouter."""

    def __init__(self) -> None:
        settings = get_settings()
        self._provider = settings.LLM_PROVIDER.lower().strip()
        self._default_model = settings.PRIMARY_MODEL or _DEFAULT_MODELS.get(self._provider, "")
        self._client = None

        self._role_models: dict[str, str] = {}
        if self._provider == PROVIDER_OPENROUTER:
            for role, attr in (
                ("reasoning", "REASONING_MODEL"),
                ("build", "BUILD_MODEL"),
                ("longcontext", "LONGCONTEXT_MODEL"),
                ("fallback", "FALLBACK_MODEL"),
            ):
                val = getattr(settings, attr, "").strip()
                if val:
                    self._role_models[role] = val

        if self._provider not in (PROVIDER_ANTHROPIC, PROVIDER_OPENAI, PROVIDER_GROQ, PROVIDER_OPENROUTER):
            logger.warning(
                "Unknown LLM_PROVIDER '%s' — falling back to anthropic", self._provider
            )
            self._provider = PROVIDER_ANTHROPIC

    def get_model_for_role(self, role: str = "primary") -> str:
        """Return the model name for a given role.

        When provider is openrouter and a role-specific model is configured,
        that model is returned. Otherwise falls back to PRIMARY_MODEL.

        Supported roles: primary, reasoning, build, longcontext, fallback.
        """
        if role == "primary" or not self._role_models:
            return self._default_model
        return self._role_models.get(role, self._default_model)

    @property
    def provider(self) -> str:
        """Current provider name."""
        return self._provider

    def _get_api_key(self) -> str:
        """Return the API key for the current provider."""
        settings = get_settings()
        key_map = {
            PROVIDER_ANTHROPIC: settings.ANTHROPIC_API_KEY,
            PROVIDER_OPENAI: settings.OPENAI_API_KEY,
            PROVIDER_GROQ: settings.GROQ_API_KEY,
            PROVIDER_OPENROUTER: settings.OPENROUTER_API_KEY,
        }
        key = key_map.get(self._provider, "")
        if not key:
            raise LLMError(
                f"No API key configured for provider '{self._provider}'. "
                f"Set the corresponding env var (e.g. GROQ_API_KEY).",
                provider=self._provider,
            )
        return key

    def _get_client(self):
        """Lazy-initialize the appropriate SDK client."""
        if self._client is None:
            api_key = self._get_api_key()
            settings = get_settings()
            timeout_s = float(getattr(settings, "LLM_TIMEOUT_S", 120.0) or 120.0)

            if self._provider == PROVIDER_ANTHROPIC:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s)
            else:
                from openai import AsyncOpenAI
                kwargs = {"api_key": api_key, "timeout": timeout_s}
                if self._provider in _BASE_URLS:
                    kwargs["base_url"] = _BASE_URLS[self._provider]
                if self._provider == PROVIDER_OPENROUTER:
                    kwargs["default_headers"] = {
                        "HTTP-Referer": "https://fs-intelligence-platform.app",
                        "X-Title": "FS Intelligence Platform",
                    }
                self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def call_llm(
        self,
        prompt: str,
        system: str = "",
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        role: str = "primary",
    ) -> str:
        """Send a prompt to the LLM and return the text response.

        Args:
            prompt: The user message.
            system: Optional system prompt.
            model: Override the default model (takes precedence over role).
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
            role: Model role for automatic routing (primary/reasoning/build/longcontext/fallback).

        Returns:
            The LLM's text response.

        Raises:
            LLMError: If the API call fails.
        """
        use_model = model or self.get_model_for_role(role)
        client = self._get_client()

        logger.info("LLM call → provider=%s, model=%s, prompt_len=%d", self._provider, use_model, len(prompt))

        try:
            if self._provider == PROVIDER_ANTHROPIC:
                return await self._call_anthropic(client, prompt, system, use_model, max_tokens, temperature)
            else:
                return await self._call_openai_compat(client, prompt, system, use_model, max_tokens, temperature)
        except LLMError:
            raise
        except Exception as exc:
            logger.exception("LLM call failed: %s", exc)
            raise LLMError(
                f"LLM call failed: {exc}",
                provider=self._provider,
                model=use_model,
            ) from exc

    async def _call_openai_compat(self, client, prompt, system, model, max_tokens, temperature) -> str:
        """Call OpenAI-compatible API (OpenAI, Groq, OpenRouter)."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        text = response.choices[0].message.content or ""
        usage = response.usage
        if usage:
            logger.info(
                "LLM response ← provider=%s, model=%s, tokens_in=%d, tokens_out=%d",
                self._provider, model,
                usage.prompt_tokens or 0,
                usage.completion_tokens or 0,
            )
        if not text.strip():
            raise LLMError(
                f"LLM returned empty response (model={model})",
                provider=self._provider,
                model=model,
            )
        return text

    async def _call_anthropic(self, client, prompt, system, model, max_tokens, temperature) -> str:
        """Call Anthropic API."""
        import anthropic

        message = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system if system else anthropic.NOT_GIVEN,
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text
        logger.info(
            "LLM response ← provider=%s, model=%s, tokens_in=%d, tokens_out=%d",
            self._provider, model,
            message.usage.input_tokens,
            message.usage.output_tokens,
        )
        return text

    async def call_llm_json(
        self,
        prompt: str,
        system: str = "",
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        role: str = "primary",
    ) -> dict:
        """Call LLM and parse the response as JSON.

        Extracts JSON from the response, handling common LLM quirks
        like wrapping in ```json blocks.

        Returns:
            Parsed JSON as a dictionary.

        Raises:
            LLMError: If the call fails or JSON parsing fails.
        """
        text = await self.call_llm(prompt, system, model, max_tokens, temperature, role=role)

        # Strip markdown code block wrappers if present
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        def _try_load(s: str):
            return json.loads(s)

        # 1) Direct parse
        try:
            return _try_load(cleaned)
        except json.JSONDecodeError:
            pass

        # 2) Extract the first JSON array/object substring (handles leading prose like
        # "Sure — here's the JSON:" then the payload).
        start_match = re.search(r"[\[{]", cleaned)
        if start_match:
            start = start_match.start()
            tail = cleaned[start:]

            # Prefer slicing to the last closing bracket/brace.
            last_bracket = tail.rfind("]")
            last_brace = tail.rfind("}")
            end = max(last_bracket, last_brace)
            if end != -1:
                candidate = tail[: end + 1].strip()
                try:
                    return _try_load(candidate)
                except json.JSONDecodeError:
                    pass

            # As a last resort try the full tail.
            try:
                return _try_load(tail.strip())
            except json.JSONDecodeError:
                pass

        logger.error("Failed to parse LLM JSON response.\nRaw (first 800 chars): %s", text[:800])
        raise LLMError(
            "LLM returned invalid JSON (could not extract a valid JSON object/array).",
            provider=self._provider,
            model=model or self.get_model_for_role(role),
        )

    async def check_health(self) -> bool:
        """Quick health check — verifies the API key is valid."""
        try:
            client = self._get_client()
            if self._provider == PROVIDER_ANTHROPIC:
                await client.messages.create(
                    model=self._default_model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "ping"}],
                )
            else:
                await client.chat.completions.create(
                    model=self._default_model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "ping"}],
                )
            return True
        except Exception as exc:
            logger.warning("LLM health check failed: %s", exc)
            return False


# ── Module-level convenience function ──────────────────

async def call_llm(prompt: str, **kwargs) -> str:
    """Convenience wrapper — imports the singleton and calls it."""
    from app.llm import get_llm_client
    client = get_llm_client()
    return await client.call_llm(prompt, **kwargs)
