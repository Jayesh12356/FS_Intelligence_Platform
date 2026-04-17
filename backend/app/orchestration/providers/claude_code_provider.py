"""Claude Code Provider — true CLI-first LLM with graceful fallback.

Architecture:
  - call_llm: Tries the Claude CLI first (``--output-format stream-json``).
    Parses assistant content blocks *and* the final ``result`` field.
    If sufficient text is extracted, returns it.  If the CLI produces
    empty/insufficient content (common with external models via OpenRouter),
    raises LLMError so the orchestration bridge falls back to Direct API.
  - build_task: Uses the Claude CLI in agent mode with MCP tools.
  - check_health: Verifies the CLI is installed and reachable.
"""

import asyncio
import json
import logging
import subprocess
from typing import Any

from app.config import get_settings
from app.llm.client import LLMError
from app.orchestration.base import BuildResult, ExecutionProvider

logger = logging.getLogger(__name__)

MIN_USEFUL_RESPONSE_LENGTH = 50


def _run_cli(
    args: list[str], timeout: int = 120, cwd: str | None = None
) -> subprocess.CompletedProcess:
    """Run the Claude CLI synchronously (called via ``asyncio.to_thread``)."""
    return subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        cwd=cwd,
    )


def _extract_text_from_stream(stdout_bytes: bytes) -> str:
    """Extract meaningful text from ``--output-format stream-json`` output.

    The stream contains one JSON object per line.  We look at two sources:

    1. ``type: "assistant"`` events whose ``message.content`` array contains
       ``{"type": "text", "text": "..."}`` blocks — the raw model output.
    2. The final ``type: "result"`` event with a ``result`` string — the
       aggregated answer (populated by Anthropic models, often empty with
       external models).

    We collect text from *both* sources and return whichever is longer.
    """
    raw = stdout_bytes.decode(errors="replace").strip()
    if not raw:
        return ""

    assistant_texts: list[str] = []
    result_text = ""

    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        obj_type = obj.get("type", "")

        if obj_type == "assistant":
            content = (obj.get("message") or {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        txt = block.get("text", "").strip()
                        if txt:
                            assistant_texts.append(txt)

        elif obj_type == "result":
            r = obj.get("result", "")
            if isinstance(r, str) and r.strip():
                result_text = r.strip()

    combined_assistant = "\n".join(assistant_texts).strip()

    if len(result_text) >= len(combined_assistant):
        return result_text
    return combined_assistant


class ClaudeCodeProvider(ExecutionProvider):
    """CLI-first LLM provider: tries Claude Code CLI, falls back via bridge."""

    name = "claude_code"
    display_name = "Claude Code (CLI Agent)"
    capabilities = ["llm", "build"]
    llm_selectable = True
    health_note = (
        "Requires Claude Code CLI installed and authenticated (claude login). "
        "Tries CLI for text generation; falls back to Direct API if CLI "
        "returns insufficient content. Builds always use the CLI agent."
    )

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
        """Try Claude CLI first; raise LLMError on empty so bridge can fall back."""
        cli = self._cli_path()
        full_prompt = prompt
        if system:
            full_prompt = f"System: {system}\n\n{prompt}"

        try:
            result = await asyncio.to_thread(
                _run_cli,
                [cli, "-p", full_prompt, "--output-format", "stream-json", "--verbose"],
                timeout=120,
            )

            if result.returncode != 0:
                err_msg = result.stderr.decode(errors="replace").strip()
                logger.error(
                    "Claude CLI failed (exit %d): %s", result.returncode, err_msg
                )
                raise LLMError(
                    f"Claude CLI failed: {err_msg or 'unknown error'}",
                    provider="claude_code",
                    model="",
                )

            text = _extract_text_from_stream(result.stdout)

            if len(text) < MIN_USEFUL_RESPONSE_LENGTH:
                logger.warning(
                    "Claude CLI returned insufficient content (%d chars). "
                    "Triggering fallback to Direct API.",
                    len(text),
                )
                raise LLMError(
                    "Claude CLI returned insufficient content for text generation. "
                    "Falling back to Direct API.",
                    provider="claude_code",
                    model="",
                )

            logger.info(
                "Claude CLI returned %d chars of content", len(text)
            )
            return text

        except LLMError:
            raise
        except FileNotFoundError:
            raise LLMError(
                f"Claude CLI not found at {cli!r}. "
                "Install: npm install -g @anthropic-ai/claude-code, then run claude login.",
                provider="claude_code",
                model="",
            ) from None
        except subprocess.TimeoutExpired:
            raise LLMError(
                "Claude CLI timed out after 120 s",
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
            cli, "-p", build_prompt,
            "--allowedTools", "mcp__fs-intelligence-platform__*",
        ]
        if mcp_config:
            args.extend(["--mcp-config", mcp_config])

        try:
            result = await asyncio.to_thread(
                _run_cli, args, timeout=300, cwd=output_folder
            )
            return BuildResult(
                success=result.returncode == 0,
                output=result.stdout.decode(errors="replace").strip(),
                error=(
                    result.stderr.decode(errors="replace").strip()
                    if result.returncode != 0
                    else None
                ),
            )
        except Exception as exc:
            return BuildResult(success=False, error=str(exc))

    async def check_health(self) -> bool:
        cli = self._cli_path()
        try:
            result = await asyncio.to_thread(
                _run_cli, [cli, "--version"], timeout=10
            )
            return result.returncode == 0
        except FileNotFoundError:
            logger.warning("Claude CLI not found at %r", cli)
            return False
        except subprocess.TimeoutExpired:
            logger.warning("Claude CLI health check timed out")
            return False
        except Exception as exc:
            logger.warning(
                "Claude health check failed: %s: %s", type(exc).__name__, exc
            )
            return False
