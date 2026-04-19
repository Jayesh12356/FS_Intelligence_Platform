"""Claude Code Provider — CLI-only LLM.

Architecture:
  - call_llm: Runs the Claude CLI (``--output-format json``) and parses
    the single-blob response.  Any failure (missing CLI, bad exit code,
    insufficient content, timeout, non-Anthropic routing) is raised as
    :class:`LLMError` so the orchestration bridge can surface it.  The
    bridge **does not** fall back to the Direct API when ``claude_code``
    is the selected provider (see ``NO_FALLBACK_PROVIDERS`` in
    ``app.orchestration.llm_bridge``): that would leak tokens to
    OpenRouter/Anthropic credits the user did not authorise.
  - build_task: Uses the Claude CLI in agent mode with MCP tools.
  - check_health: Verifies the CLI is installed, authenticated, and
    actually emits text for a live ping (cached for 60 s).

Guardrails against wasted tokens:
  - A pre-flight config check inspects ``~/.claude/settings.json`` and
    the ``ANTHROPIC_*`` env vars.  If the CLI is pointed at a
    non-Anthropic base URL or model (e.g. OpenRouter routing
    ``xiaomi/mimo-v2-flash``), Claude Code's print mode silently returns
    ``result: ""`` after billing the user.  We refuse the request up
    front with an actionable error.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.llm.client import LLMError
from app.orchestration.base import BuildResult, ExecutionProvider

logger = logging.getLogger(__name__)

MIN_USEFUL_RESPONSE_LENGTH = 20

# Anthropic-native model families the CLI's print mode works well with.
# Anything else (OpenRouter proxies, DeepSeek, Mixtral, xiaomi/*, etc.)
# tends to come back with an empty ``result`` field after burning tokens.
_ANTHROPIC_MODEL_RE = re.compile(r"^(?:claude[-_\w]*|sonnet\b|haiku\b|opus\b)", re.IGNORECASE)


def _resolve_cli_invocation(cli: str) -> list[str]:
    """Resolve ``cli`` to an argv prefix safe for cross-platform invocation.

    On Windows, ``claude`` is a ``.cmd`` batch wrapper that re-invokes
    ``node cli.js``.  Python's :func:`subprocess.run` routes every ``.cmd``
    call through ``cmd.exe``, which transcodes non-ASCII argv via the OEM
    codepage — so em-dashes, smart quotes, and any other non-latin-1 glyph
    that appears in our pipeline prompts are silently replaced with ``?``
    and the CLI emits an empty response.  To sidestep this we find the
    sibling ``cli.js`` and invoke ``node`` directly, which Python routes
    through :c:`CreateProcessW` with full UTF-16 argv fidelity.

    On non-Windows platforms we return ``[cli]`` unchanged.
    """
    if sys.platform != "win32":
        return [cli]

    resolved = shutil.which(cli) or cli
    lowered = resolved.lower()
    if not lowered.endswith((".cmd", ".bat")):
        return [resolved]

    base_dir = os.path.dirname(resolved)
    cli_js = os.path.join(base_dir, "node_modules", "@anthropic-ai", "claude-code", "cli.js")
    if os.path.exists(cli_js):
        return ["node", cli_js]

    logger.warning(
        "Claude CLI .cmd wrapper found at %r but sibling cli.js not located; "
        "falling back to the wrapper (non-ASCII prompts may be mangled).",
        resolved,
    )
    return [resolved]


def _run_cli(
    args: list[str],
    timeout: int = 120,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run the Claude CLI synchronously (called via ``asyncio.to_thread``).

    ``env`` is passed through unchanged when provided so callers can
    inject ``MCP_SESSION_ID`` / ``BACKEND_URL`` for telemetry. When
    ``None`` we let subprocess inherit the parent's environment, which
    preserves the previous behavior.
    """
    return subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=timeout,
        cwd=cwd,
        env=env,
    )


def _is_anthropic_model_id(model: str | None) -> bool:
    if not model:
        return False
    return bool(_ANTHROPIC_MODEL_RE.match(model.strip()))


def _load_claude_settings() -> dict[str, Any]:
    """Best-effort load of ``~/.claude/settings.json``.  Returns ``{}`` on any failure."""
    try:
        path = Path.home() / ".claude" / "settings.json"
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to read ~/.claude/settings.json: %s", exc)
        return {}


def _detect_non_anthropic_routing() -> str | None:
    """Return a human-readable reason string if the CLI is misrouted, else None.

    The Claude Code CLI supports "bring your own model" via the
    ``ANTHROPIC_BASE_URL`` env var or ``env`` block in
    ``~/.claude/settings.json``.  When pointed at a non-Anthropic proxy
    (OpenRouter, LocalAI, etc.), print mode (``-p``) frequently returns
    ``result: ""`` — the CLI still bills the upstream, but our pipeline
    gets nothing.  We detect this up front so we can refuse the call
    instead of silently burning money on every request.
    """
    # Env vars take precedence over ~/.claude/settings.json at CLI runtime.
    env_base = os.environ.get("ANTHROPIC_BASE_URL", "").strip()
    env_model = os.environ.get("ANTHROPIC_MODEL", "").strip()
    settings = _load_claude_settings()
    cfg_env = settings.get("env") or {}
    cfg_base = str(cfg_env.get("ANTHROPIC_BASE_URL", "") or "").strip()
    cfg_model = str(cfg_env.get("ANTHROPIC_MODEL", "") or "").strip()

    effective_base = env_base or cfg_base
    effective_model = env_model or cfg_model

    if effective_base:
        lowered = effective_base.lower()
        if not any(host in lowered for host in ("anthropic.com", "anthropic.ai", "claude.ai")):
            return (
                f"Claude CLI is configured to proxy through a non-Anthropic "
                f"base URL ({effective_base!r}). Print mode returns empty "
                f"output on this setup and still bills tokens. Fix: unset "
                f"ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_MODEL, "
                f"remove the `env` block from ~/.claude/settings.json, and "
                f"run `claude /login` with an Anthropic account — or switch "
                f"the Document LLM provider to Direct API in Settings."
            )

    if effective_model and not _is_anthropic_model_id(effective_model):
        return (
            f"Claude CLI is pinned to a non-Anthropic model "
            f"({effective_model!r}). Print mode cannot reliably emit text "
            f"with external models and still bills tokens. Fix: unset "
            f"ANTHROPIC_MODEL or set it to an Anthropic model (e.g. "
            f"'claude-sonnet-4-20250514'), or switch the Document LLM "
            f"provider to Direct API in Settings."
        )

    return None


def _parse_json_output(stdout_bytes: bytes) -> dict[str, Any]:
    """Parse ``--output-format json`` (a single JSON object on stdout).

    Returns ``{}`` if parsing fails — callers treat that as an empty
    response and raise an appropriate error.
    """
    raw = stdout_bytes.decode(errors="replace").strip()
    if not raw:
        return {}
    # The CLI occasionally prints a warning line before the JSON blob when
    # stdin is not a TTY ("Warning: no stdin data received in 3s...").  Find
    # the first ``{`` and parse from there.
    start = raw.find("{")
    if start < 0:
        return {}
    try:
        return json.loads(raw[start:])
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse Claude CLI JSON (%s): %.300r", exc, raw)
        return {}


def _non_anthropic_models_in_usage(usage: dict[str, Any]) -> list[str]:
    if not isinstance(usage, dict):
        return []
    return [m for m in usage.keys() if not _is_anthropic_model_id(m)]


class ClaudeCodeProvider(ExecutionProvider):
    """CLI-first LLM provider: tries Claude Code CLI, falls back via bridge."""

    name = "claude_code"
    display_name = "Claude Code (CLI Agent)"
    capabilities = ["llm", "build"]
    llm_selectable = True
    health_note = (
        "Requires Claude Code CLI installed and authenticated with an "
        "Anthropic account (claude /login). The CLI must NOT be routed "
        "through OpenRouter/other proxies — print mode returns empty "
        "content with non-Anthropic models and still bills tokens. If "
        "the health check fails, either run `claude /login` with an "
        "Anthropic account, or switch Document LLM to Direct API."
    )

    _HEALTH_TTL = 60.0  # seconds
    _health_cache: tuple[float, bool, str] | None = None

    def _cli_path(self) -> str:
        return get_settings().CLAUDE_CODE_CLI_PATH or "claude"

    async def call_llm(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        """Invoke the Claude Code CLI in print mode and return the text.

        Uses ``--output-format json`` so we can inspect ``modelUsage`` /
        ``is_error`` and fail loudly when the CLI is misconfigured.  The
        caller's system prompt is forwarded via ``--append-system-prompt``
        — inlining it inside the user turn causes the CLI to treat it as
        chit-chat and return a 30-char brush-off.
        """
        # Pre-flight: refuse to spend tokens if the CLI is obviously misrouted.
        misroute_reason = _detect_non_anthropic_routing()
        if misroute_reason:
            logger.error("Claude CLI pre-flight refused: %s", misroute_reason)
            raise LLMError(
                f"Claude Code is not usable as a Document LLM on this machine. {misroute_reason}",
                provider="claude_code",
                model="",
            )

        cli = self._cli_path()
        cli_argv = _resolve_cli_invocation(cli)

        args = [*cli_argv, "-p", prompt, "--output-format", "json"]
        if system:
            args.extend(["--append-system-prompt", system])

        # Honour the configured LLM_TIMEOUT_S so long analyze/refine prompts
        # (which blow past the legacy 180 s hard-coded value) don't surface as
        # a bare ReadTimeout — and so the perfection loop's
        # LLMTimeoutBackoff repair can lift the ceiling by setting the env var.
        timeout_s = int(max(30, float(get_settings().LLM_TIMEOUT_S) * 1.5))
        try:
            result = await asyncio.to_thread(_run_cli, args, timeout=timeout_s)

            if result.returncode != 0:
                err_msg = result.stderr.decode(errors="replace").strip()
                logger.error("Claude CLI failed (exit %d): %s", result.returncode, err_msg)
                raise LLMError(
                    f"Claude CLI failed: {err_msg or 'unknown error'}",
                    provider="claude_code",
                    model="",
                )

            payload = _parse_json_output(result.stdout)
            if not payload:
                raise LLMError(
                    "Claude CLI returned no parseable output. This usually "
                    "means the CLI silently crashed or emitted only a "
                    "warning line; re-run `claude /login` and check "
                    "`claude doctor`.",
                    provider="claude_code",
                    model="",
                )

            if payload.get("is_error"):
                detail = payload.get("result") or payload.get("error") or "unknown error"
                raise LLMError(
                    f"Claude CLI reported is_error=true: {detail}",
                    provider="claude_code",
                    model="",
                )

            text = str(payload.get("result", "") or "").strip()
            usage = payload.get("modelUsage") or {}
            non_anthropic = _non_anthropic_models_in_usage(usage)

            if len(text) < MIN_USEFUL_RESPONSE_LENGTH:
                # Differentiate the "clearly misconfigured" case from a
                # genuine "model refused" response, so the user can act.
                if non_anthropic:
                    models = ", ".join(sorted(non_anthropic))
                    cost = payload.get("total_cost_usd")
                    cost_note = f" (cost billed: ${cost:.4f})" if isinstance(cost, (int, float)) else ""
                    raise LLMError(
                        f"Claude CLI returned empty text after routing the "
                        f"request through non-Anthropic model(s): {models}"
                        f"{cost_note}. Print mode does not work with "
                        f"external models. Fix: `claude /login` with an "
                        f"Anthropic account, or switch Document LLM to "
                        f"Direct API in Settings.",
                        provider="claude_code",
                        model="",
                    )

                snippet = text[:200] if text else "(empty)"
                logger.warning(
                    "Claude CLI returned insufficient content (%d chars): %s",
                    len(text),
                    snippet,
                )
                raise LLMError(
                    "Claude CLI returned insufficient content for text "
                    f"generation (got {len(text)} chars: {snippet!r}). "
                    "Fallback to Direct API is disabled for the claude_code "
                    "provider (token protection); please re-run `claude "
                    "/login` or switch Document LLM to Direct API.",
                    provider="claude_code",
                    model="",
                )

            logger.info(
                "Claude CLI returned %d chars of content (models=%s)",
                len(text),
                list(usage.keys()),
            )
            return text

        except LLMError:
            raise
        except FileNotFoundError:
            raise LLMError(
                f"Claude CLI not found at {cli!r}. "
                "Install: npm install -g @anthropic-ai/claude-code, then run claude /login.",
                provider="claude_code",
                model="",
            ) from None
        except subprocess.TimeoutExpired:
            raise LLMError(
                f"Claude CLI timed out after {timeout_s} s "
                f"(LLM_TIMEOUT_S={get_settings().LLM_TIMEOUT_S}). "
                "Raise LLM_TIMEOUT_S or shorten the prompt.",
                provider="claude_code",
                model="",
            ) from None

    async def build_task(
        self,
        task_context: dict,
        output_folder: str,
        **kwargs: Any,
    ) -> BuildResult:
        """Use Claude CLI agent mode for autonomous builds with MCP tools."""
        cli = self._cli_path()
        mcp_config = kwargs.get("mcp_config", "")

        build_prompt = (
            f"You are building a task from an FS specification.\n"
            f"Task: {task_context.get('title', 'Unknown')}\n"
            f"Description: {task_context.get('description', '')}\n"
            f"Output folder: {output_folder}\n"
            f"Create the required files in the output folder.\n"
        )

        args = [
            *_resolve_cli_invocation(cli),
            "-p",
            build_prompt,
            "--allowedTools",
            "mcp__fs-intelligence-platform__*",
        ]
        if mcp_config:
            args.extend(["--mcp-config", mcp_config])

        try:
            result = await asyncio.to_thread(_run_cli, args, timeout=300, cwd=output_folder)
            return BuildResult(
                success=result.returncode == 0,
                output=result.stdout.decode(errors="replace").strip(),
                error=(result.stderr.decode(errors="replace").strip() if result.returncode != 0 else None),
            )
        except Exception as exc:
            return BuildResult(success=False, error=str(exc))

    async def check_health(self) -> bool:
        """Verify the CLI is present, authenticated, and emits real text.

        Health is cached for :attr:`_HEALTH_TTL` seconds so the Settings
        page can poll without hammering the CLI.  A failure here is what
        the UI uses to paint the Claude Code provider red *before* the
        user tries to run a guided-discovery flow.
        """
        now = time.monotonic()
        cached = type(self)._health_cache
        if cached and (now - cached[0]) < self._HEALTH_TTL:
            return cached[1]

        healthy, reason = await self._probe_health()
        type(self)._health_cache = (now, healthy, reason)
        if not healthy:
            logger.warning("Claude Code provider health: unhealthy — %s", reason)
        return healthy

    async def _probe_health(self) -> tuple[bool, str]:
        cli = self._cli_path()
        try:
            version = await asyncio.to_thread(
                _run_cli,
                [*_resolve_cli_invocation(cli), "--version"],
                timeout=10,
            )
            if version.returncode != 0:
                return False, "CLI --version exited non-zero"
        except FileNotFoundError:
            return False, f"CLI not found at {cli!r}"
        except subprocess.TimeoutExpired:
            return False, "CLI --version timed out"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

        misroute = _detect_non_anthropic_routing()
        if misroute:
            return False, misroute

        # Live ping — must emit non-empty text, otherwise the provider is
        # unusable for text generation even if --version worked.
        try:
            args = [
                *_resolve_cli_invocation(cli),
                "-p",
                "Reply with the single word: OK",
                "--output-format",
                "json",
            ]
            probe = await asyncio.to_thread(_run_cli, args, timeout=45)
            if probe.returncode != 0:
                return False, f"ping exit {probe.returncode}"
            payload = _parse_json_output(probe.stdout)
            if not payload:
                return False, "ping produced no JSON output"
            if payload.get("is_error"):
                return False, f"ping reported is_error: {payload.get('result') or payload.get('error')}"
            text = str(payload.get("result", "") or "").strip()
            if len(text) < 1:
                usage = payload.get("modelUsage") or {}
                non_anthropic = _non_anthropic_models_in_usage(usage)
                if non_anthropic:
                    return False, (
                        "CLI returned empty text after routing through "
                        f"non-Anthropic model(s): {', '.join(non_anthropic)}. "
                        "Print mode only works with Anthropic models."
                    )
                return False, "CLI returned empty text for a trivial ping"
            return True, "ok"
        except subprocess.TimeoutExpired:
            return False, "live ping timed out after 45 s"
        except Exception as exc:  # noqa: BLE001
            return False, f"live ping {type(exc).__name__}: {exc}"
