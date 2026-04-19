"""Mock LLM provider — deterministic fixture-backed responses for the perfection loop.

Purpose
-------
The perfection verification loop runs thousands of pipeline iterations. Real
LLM calls would be slow, flaky, and expensive. The ``mock`` provider short-
circuits every LLM call to a canned response keyed by the prompt "class":

* ambiguity   — ``{"ambiguities": []}``
* contradiction — ``{"contradictions": []}``
* edge_case   — ``{"gaps": []}``
* quality     — ``{"quality_score": 85, "completeness": 85, "clarity": 85, "consistency": 85}``
* task        — a minimal tasks array based on the TODO-API scenario
* dependency  — ``{"dependencies": []}``
* impact      — ``{"change_impacts": []}``
* reverse_fs  — ``{"sections": [...]}``
* idea / generate-fs — ``{"title": "...", "sections": [...]}``

Fixture JSON files live under ``backend/tests/fixtures/llm_responses``. Drop
new files there to override or extend responses. If no fixture matches the
prompt, a neutral ``{}`` response is returned so downstream json parsers
don't crash.

Selection
---------
Users opt in by setting ``LLM_PROVIDER=mock`` in the environment, or by
writing ``"mock"`` into ``ToolConfigDB.llm_provider`` for tests. The
provider is registered via ``app.orchestration.registry`` only when the
env var is set, so production never picks it up accidentally.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from app.orchestration.base import BuildResult, ExecutionProvider

logger = logging.getLogger(__name__)

_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "llm_responses"


def _load_fixtures() -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not _FIXTURE_DIR.is_dir():
        return out
    for p in _FIXTURE_DIR.glob("*.json"):
        try:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skipping invalid fixture %s: %s", p, exc)
    return out


_FIXTURES: dict[str, Any] | None = None


def _fixtures() -> dict[str, Any]:
    global _FIXTURES
    if _FIXTURES is None:
        _FIXTURES = _load_fixtures()
    return _FIXTURES


def reset_fixture_cache() -> None:
    """Force re-read of fixtures (used by tests that mutate fixture files)."""
    global _FIXTURES
    _FIXTURES = None


# Ordered: earlier patterns take precedence. Each entry maps a regex to the
# fixture-file basename (without extension) that we return for matching prompts.
_PROMPT_MATCHERS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ambigu", re.I), "ambiguity"),
    (re.compile(r"contradict", re.I), "contradiction"),
    (re.compile(r"edge[-_ ]*case", re.I), "edge_case"),
    (re.compile(r"quality", re.I), "quality"),
    (re.compile(r"task.*decompos|atomic task", re.I), "task"),
    (re.compile(r"dependenc", re.I), "dependency"),
    (re.compile(r"impact", re.I), "impact"),
    (re.compile(r"reverse.*fs|functional specification from code", re.I), "reverse_fs"),
    (re.compile(r"idea|generate.*fs|functional specification", re.I), "idea"),
    (re.compile(r"test[-_ ]*case", re.I), "testcase"),
    (re.compile(r"refine|rewrite|suggestion", re.I), "refine"),
]


def classify_prompt(prompt: str, system: str = "") -> str:
    """Return the fixture key for a given prompt, or ``"default"`` if no match."""
    blob = f"{system}\n\n{prompt}"
    for pattern, key in _PROMPT_MATCHERS:
        if pattern.search(blob):
            return key
    return "default"


def render_mock_response(prompt: str, system: str = "") -> str:
    """Look up the fixture for this prompt; return a JSON string (or empty object)."""
    key = classify_prompt(prompt, system)
    fixtures = _fixtures()
    if key in fixtures:
        return json.dumps(fixtures[key], ensure_ascii=False)
    # Permissive fallback: every pipeline node json-parses its response, so
    # ``{}`` is always safe (usually yields an empty list of findings).
    return "{}"


class MockProvider(ExecutionProvider):
    """Deterministic in-process LLM provider for perfection-loop / unit runs."""

    name = "mock"
    display_name = "Mock (deterministic fixtures)"
    capabilities = ["llm", "build"]
    llm_selectable = False  # never offered in the UI
    health_note = "Deterministic fixture-backed provider for tests only."

    async def call_llm(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        logger.debug("MockProvider.call_llm prompt[:80]=%r", prompt[:80])
        return render_mock_response(prompt, system)

    async def build_task(
        self,
        task_context: dict,
        output_folder: str,
        **kwargs: Any,
    ) -> BuildResult:
        # "Building" is a no-op in mock mode. Write a marker file so e2e
        # tests can assert a build artifact appeared.
        try:
            Path(output_folder).mkdir(parents=True, exist_ok=True)
            marker = Path(output_folder) / "MOCK_BUILD_DONE.txt"
            marker.write_text(
                f"mock build for task {task_context.get('id', '?')}\n",
                encoding="utf-8",
            )
            return BuildResult(success=True, files_created=[str(marker)], output="mock build ok")
        except Exception as exc:
            return BuildResult(success=False, error=str(exc))

    async def check_health(self) -> bool:
        return True


def mock_provider_enabled() -> bool:
    """Return True when the mock provider should be registered.

    Active when either the ``LLM_PROVIDER`` env var is ``mock`` or the
    ``PERFECTION_LOOP`` flag is set. Wiring it only on opt-in keeps
    production behavior unchanged.
    """
    return os.environ.get("LLM_PROVIDER", "").strip().lower() == "mock" or os.environ.get("PERFECTION_LOOP", "") == "1"
