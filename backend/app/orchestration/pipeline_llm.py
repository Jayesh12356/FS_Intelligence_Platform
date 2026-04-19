"""Unified LLM caller for pipeline nodes (0.4.0+).

Every pipeline LLM call is routed through :func:`orchestrated_call_llm`
in :mod:`app.orchestration.llm_bridge`. That bridge resolves the
provider configured in ``ToolConfigDB`` and calls exactly that provider
— no silent fallbacks, no hidden Direct-API path.

Why no feature flag
-------------------

Earlier versions had an ``ORCHESTRATION_ENABLED`` flag that, when false,
routed every call straight through :class:`LLMClient`. That path
ignored the user's Settings choice and leaked tokens to OpenRouter even
when the user had selected ``cursor`` or ``claude_code``. The flag is
removed as of 0.4.0; orchestration is the only path.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Union

logger = logging.getLogger(__name__)


class LLMJSONParseError(ValueError):
    """Raised when an LLM response can't be parsed as JSON after retries."""

    def __init__(self, message: str, *, raw: str | None = None):
        super().__init__(message)
        self.raw = raw


async def pipeline_call_llm(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.0,
    role: str = "primary",
    model: str | None = None,  # noqa: ARG001 — reserved; providers pick their own model
    **kwargs: Any,
) -> str:
    """LLM caller for pipeline nodes. Always routes through the orchestrator."""

    from app.llm.retry import llm_retry
    from app.orchestration.llm_bridge import orchestrated_call_llm

    async def _orch() -> str:
        return await orchestrated_call_llm(
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            role=role,
            **kwargs,
        )

    return await llm_retry(_orch, label=f"pipeline_call_llm[{role}]")


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.DOTALL)


def _strip_code_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*\n?", "", s, flags=re.IGNORECASE)
    if s.rstrip().endswith("```"):
        s = re.sub(r"\n?```\s*$", "", s.rstrip())
    return s.strip()


def _extract_first_json_blob(text: str) -> str | None:
    """Find the first balanced {...} or [...] blob in text, if any."""
    stripped = text.strip()
    start_chars = "[{"
    end_for = {"{": "}", "[": "]"}
    for i, ch in enumerate(stripped):
        if ch in start_chars:
            depth = 0
            end = end_for[ch]
            in_str = False
            esc = False
            for j in range(i, len(stripped)):
                c = stripped[j]
                if esc:
                    esc = False
                    continue
                if c == "\\":
                    esc = True
                    continue
                if c == '"':
                    in_str = not in_str
                    continue
                if in_str:
                    continue
                if c == ch:
                    depth += 1
                elif c == end:
                    depth -= 1
                    if depth == 0:
                        return stripped[i : j + 1]
            break
    return None


def _try_parse_json(text: str) -> Union[dict, list, None]:
    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    blob = _extract_first_json_blob(cleaned)
    if blob is not None:
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            return None
    return None


async def pipeline_call_llm_json(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.0,
    role: str = "primary",
    model: str | None = None,  # noqa: ARG001 — providers choose their own model
    **kwargs: Any,
) -> Union[dict, list]:
    """JSON variant of :func:`pipeline_call_llm` with robust fallback parsing.

    Strategy:
      1. Call the LLM via the orchestrator.
      2. Try ``json.loads`` after stripping code fences.
      3. If that fails, search for the first balanced JSON blob.
      4. If that fails, retry once with a stricter prompt asking for pure JSON.
      5. If still failing, raise :class:`LLMJSONParseError`.
    """
    from app.orchestration.llm_bridge import orchestrated_call_llm

    async def _invoke(p: str, s: str) -> str:
        return await orchestrated_call_llm(
            prompt=p,
            system=s,
            max_tokens=max_tokens,
            temperature=temperature,
            role=role,
            **kwargs,
        )

    raw = await _invoke(prompt, system)
    parsed = _try_parse_json(raw)
    if parsed is not None:
        return parsed

    logger.warning("LLM returned non-JSON; retrying once with stricter prompt (len=%d)", len(raw))
    strict_system = (
        system.strip() + "\n\n" if system else ""
    ) + "CRITICAL: respond ONLY with valid JSON. No prose, no markdown, no code fences."
    strict_prompt = (
        prompt
        + "\n\nReply ONLY with a single valid JSON value. "
        + "Do not include explanations, greetings, or code fences."
    )
    raw2 = await _invoke(strict_prompt, strict_system)
    parsed2 = _try_parse_json(raw2)
    if parsed2 is not None:
        return parsed2

    logger.error("LLM JSON parse failed after retry. First 500 chars: %r", raw2[:500])
    raise LLMJSONParseError(
        "LLM response could not be parsed as JSON after retry.",
        raw=raw2,
    )
