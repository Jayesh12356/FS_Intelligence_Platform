"""One-shot mega-prompt builders for the Cursor paste-per-action flow.

Each builder returns a self-contained markdown prompt that bundles

1. identity / role ("You are operating inside Cursor …"),
2. strict JSON / markdown output schema,
3. every piece of input context inline,
4. the MCP submit tool the agent must call at the end.

Cursor pastes this prompt into its chat, runs the work locally using
the user's Cursor subscription, and then calls the matching
``submit_*`` MCP tool with the payload. No intermediate back-and-forth;
one paste, one agent turn, one submit.
"""

from __future__ import annotations

import json
import textwrap
from typing import Any
from uuid import UUID

# Tool name on the platform's MCP server (must match
# ``mcp-server/server.py``'s FastMCP ``name``).
MCP_SERVER_NAME = "fs-intelligence-platform"

# Map task kind → the MCP submit tool the agent MUST call. Keep aligned
# with ``mcp-server/tools/cursor_tasks.py``.
SUBMIT_TOOL_BY_KIND: dict[str, str] = {
    "generate_fs": "submit_generate_fs",
    "analyze": "submit_analyze",
    "reverse_fs": "submit_reverse_fs",
    "refine": "submit_refine",
    "impact": "submit_impact",
}


def _mcp_preflight_block(submit_tool: str) -> str:
    """Render the Phase-0 MCP availability gate.

    Cursor agents have, in the wild, fallen back to writing a JSON file
    at the workspace root when the platform's MCP server isn't
    registered. That silently breaks the paste-per-action handshake —
    the platform never sees the result. This block forces the agent to
    surface the missing-server condition instead of inventing a
    fallback.
    """
    return textwrap.dedent(
        f"""\
        ## Phase 0 — MCP availability check (do this FIRST)

        This task can ONLY be completed by calling the MCP tool
        `{submit_tool}` exposed by the `{MCP_SERVER_NAME}` MCP server.
        Before doing any analysis:

        1. Confirm the `{MCP_SERVER_NAME}` MCP server is connected in
           Cursor (MCP panel shows it green) and that `{submit_tool}`
           and `claim_cursor_task` are listed.
        2. If EITHER tool is missing, STOP IMMEDIATELY. Do **not**
           write the deliverable to a file at the workspace root. Do
           **not** paste the deliverable into chat. Reply with exactly
           one short message to the user:

               "FS Intelligence Platform MCP server is not connected.
                Add the JSON snippet at the bottom of this prompt to
                `.cursor/mcp.json` in the FS Intelligence Platform repo,
                fully restart Cursor, then re-paste this prompt."

           Then end your turn. The platform will keep polling — the
           user will retry once MCP is up.
        3. If both tools are present, immediately call
           `claim_cursor_task(task_id="{{task_id}}")` so the platform
           UI flips to "claimed", then proceed to the work below.

        Hard rule: the only acceptable place for the deliverable is the
        argument list of `{submit_tool}`. Files, chat output, and
        attached artefacts are never accepted as substitutes.
        """
    )


def _header(task_id: UUID | str, kind_label: str, submit_tool: str) -> str:
    preflight = _mcp_preflight_block(submit_tool).replace(
        "{{task_id}}", str(task_id)
    )
    return textwrap.dedent(
        f"""\
        You are operating inside the Cursor IDE as an autonomous agent for
        the FS Intelligence Platform. Do not ask the user follow-up
        questions. Read the context below, produce the output in the
        exact schema shown, then call the MCP tool at the bottom with
        the result. Do not paste the result to the user — only call the
        MCP tool.

        **Task:** {kind_label}
        **Task ID:** `{task_id}`

        ---

        """
    ) + preflight + "\n---\n"


# ── Generate FS ─────────────────────────────────────────────────────


def build_generate_fs_prompt(
    task_id: UUID | str,
    idea: str,
    industry: str = "",
    complexity: str = "",
) -> str:
    """Build the single prompt that turns an idea into an FS document."""
    industry_line = f"- Industry: {industry.strip()}" if industry.strip() else ""
    complexity_line = f"- Complexity: {complexity.strip()}" if complexity.strip() else ""
    meta_block = "\n".join(ln for ln in (industry_line, complexity_line) if ln)
    if meta_block:
        meta_block = "\n" + meta_block + "\n"

    return _header(
        task_id,
        "Generate Functional Specification from idea",
        SUBMIT_TOOL_BY_KIND["generate_fs"],
    ) + textwrap.dedent(
        f"""\
        ## Context

        The user provided this product idea:

        > {idea.strip()}
        {meta_block}
        ## What to produce

        Write a clear, well-structured Functional Specification document in
        markdown. It must cover:

        1. **Overview** — one-paragraph summary
        2. **Goals & Non-Goals**
        3. **User Roles / Personas**
        4. **Functional Requirements** — numbered, testable statements
        5. **Non-Functional Requirements** — performance, security,
           observability, compliance
        6. **Data Model** — entities + fields
        7. **API Surface** — endpoints and their contracts
        8. **Acceptance Criteria** — one block per requirement
        9. **Out of Scope**

        Keep it concrete and dev-ready. No placeholder TODOs.

        ## How to submit

        When the FS is ready, call the MCP tool:

        ```
        submit_generate_fs(task_id="{task_id}", fs_markdown=<FULL MARKDOWN HERE>)
        ```

        That is the end of the task. Do not write the FS back to chat;
        only pass it as the `fs_markdown` argument.
        """
    )


# ── Analyze ─────────────────────────────────────────────────────────


ANALYZE_SCHEMA = textwrap.dedent(
    """\
    {
      "quality_score": {"score": <int 0-100>, "reasoning": "<why>"},
      "ambiguities": [
        {
          "section_index": <int>,
          "section_heading": "<string>",
          "flagged_text": "<string>",
          "reason": "<string>",
          "severity": "LOW|MEDIUM|HIGH",
          "clarification_question": "<string>"
        }
      ],
      "contradictions": [
        {
          "section_a_index": <int>,
          "section_a_heading": "<string>",
          "section_b_index": <int>,
          "section_b_heading": "<string>",
          "description": "<string>",
          "severity": "LOW|MEDIUM|HIGH",
          "suggested_resolution": "<string>"
        }
      ],
      "edge_cases": [
        {
          "section_index": <int>,
          "section_heading": "<string>",
          "scenario_description": "<string>",
          "impact": "LOW|MEDIUM|HIGH",
          "suggested_addition": "<string>"
        }
      ],
      "tasks": [
        {
          "task_id": "<stable-slug-id>",
          "title": "<string>",
          "description": "<string>",
          "section_index": <int>,
          "section_heading": "<string>",
          "depends_on": ["<task_id>"],
          "acceptance_criteria": ["<string>"],
          "effort": "LOW|MEDIUM|HIGH",
          "tags": ["<string>"],
          "can_parallel": true
        }
      ]
    }
    """
)


def build_analyze_prompt(task_id: UUID | str, fs_text: str) -> str:
    return _header(
        task_id,
        "Analyze FS document",
        SUBMIT_TOOL_BY_KIND["analyze"],
    ) + textwrap.dedent(
        f"""\
        ## FS document to analyze

        ```
        {fs_text.strip()}
        ```

        ## What to produce

        Return one JSON object, matching **exactly** this schema (keys
        and value types are mandatory; unknown enum values are not
        allowed):

        ```json
        {ANALYZE_SCHEMA}
        ```

        Guidance:

        - `quality_score.score` is your overall confidence that this FS
          is implementable without clarifications.
        - `ambiguities` / `contradictions` / `edge_cases` may be empty
          lists but must still be present.
        - Every `tasks[].task_id` must be unique and stable.
        - `tasks[].depends_on` may only reference other `task_id` values
          inside this same payload.

        ## How to submit

        Call the MCP tool with the JSON object as a native argument,
        **not** a stringified JSON:

        ```
        submit_analyze(task_id="{task_id}", payload=<JSON OBJECT ABOVE>)
        ```
        """
    )


# ── Reverse FS ──────────────────────────────────────────────────────


REVERSE_SCHEMA = textwrap.dedent(
    """\
    {
      "fs_markdown": "<FULL MARKDOWN FS DERIVED FROM THE CODE>",
      "report": {
        "coverage": <float 0.0-1.0>,
        "confidence": <float 0.0-1.0>,
        "primary_language": "<string>",
        "modules": [
          {
            "name": "<string>",
            "summary": "<string>",
            "responsibilities": ["<string>"]
          }
        ],
        "user_flows": ["<string>"],
        "gaps": ["<string>"],
        "notes": "<string>"
      }
    }
    """
)


def build_reverse_fs_prompt(
    task_id: UUID | str,
    code_manifest: dict[str, Any],
    file_excerpts: list[dict[str, Any]],
) -> str:
    manifest_lines: list[str] = []
    primary_language = code_manifest.get("primary_language") or "unknown"
    total_files = code_manifest.get("total_files") or 0
    total_lines = code_manifest.get("total_lines") or 0
    languages = code_manifest.get("languages") or {}
    manifest_lines.append(f"- Primary language: {primary_language}")
    manifest_lines.append(f"- Total files: {total_files}")
    manifest_lines.append(f"- Total lines: {total_lines}")
    if languages:
        top = sorted(languages.items(), key=lambda kv: kv[1], reverse=True)[:6]
        manifest_lines.append("- Language mix: " + ", ".join(f"{name} ({count})" for name, count in top))

    excerpt_blocks: list[str] = []
    for ex in file_excerpts[:20]:
        path = ex.get("path", "unknown")
        lang = ex.get("language", "")
        body = ex.get("excerpt", "") or ""
        excerpt_blocks.append(f"### `{path}` ({lang})\n\n```\n{body.strip()}\n```\n")
    excerpts_md = "\n".join(excerpt_blocks) or "_No excerpts provided._"

    return _header(
        task_id,
        "Reverse FS from existing codebase",
        SUBMIT_TOOL_BY_KIND["reverse_fs"],
    ) + textwrap.dedent(
        f"""\
        ## Codebase manifest

        {chr(10).join(manifest_lines)}

        ## Representative file excerpts

        {excerpts_md}

        ## What to produce

        Infer the system's purpose, architecture, and behaviour from the
        code, and author a Functional Specification that would produce
        this codebase if re-implemented. Return one JSON object matching
        **exactly** this schema:

        ```json
        {REVERSE_SCHEMA}
        ```

        `report.coverage` and `report.confidence` are floats in [0, 1].
        `fs_markdown` must be a full FS (overview → functional
        requirements → data model → acceptance criteria).

        ## How to submit (the ONLY acceptable submission path)

        Call the MCP tool with native arguments:

        ```
        submit_reverse_fs(
          task_id="{task_id}",
          fs_markdown=<STRING FROM fs_markdown>,
          report=<JSON OBJECT FROM report>,
        )
        ```

        Forbidden fallbacks (these break the platform handshake):

        - Writing the deliverable to a JSON file at the workspace root
          (e.g. `reverse_fs_output.json`) "so it can be submitted
          manually" — the platform never reads it.
        - Pasting the deliverable into chat so the user can copy it.
        - Calling `submit_reverse_fs` with the FS text inside the
          `report` argument or vice-versa.

        If `submit_reverse_fs` is not available in this Cursor session,
        follow the Phase 0 escape hatch above and stop. Do not invent
        an alternative submission path.
        """
    )


# ── Refine ──────────────────────────────────────────────────────────


def build_refine_prompt(
    task_id: UUID | str,
    fs_text: str,
    accepted_flags: list[dict[str, Any]],
) -> str:
    """Build the prompt for refining an FS using accepted ambiguity answers.

    ``accepted_flags`` is a list of ``{section_index, section_heading,
    flagged_text, clarification_question, resolution_text}`` dicts. The
    Cursor agent must fold every resolution back into the FS text and
    submit the new markdown.
    """
    flag_blocks: list[str] = []
    for i, f in enumerate(accepted_flags or [], start=1):
        flag_blocks.append(
            textwrap.dedent(
                f"""\
                ### Resolution {i}
                - Section {f.get("section_index", "?")}: {f.get("section_heading", "")}
                - Ambiguous text: "{(f.get("flagged_text") or "").strip()}"
                - Question: {f.get("clarification_question", "")}
                - User answer: {f.get("resolution_text", "")}
                """
            ).rstrip()
        )
    resolutions_md = "\n\n".join(flag_blocks) or "_No accepted resolutions._"

    return _header(
        task_id,
        "Refine FS document using accepted ambiguity resolutions",
        SUBMIT_TOOL_BY_KIND["refine"],
    ) + textwrap.dedent(
        f"""\
        ## FS document to refine

        ```
        {fs_text.strip()}
        ```

        ## Accepted resolutions

        {resolutions_md}

        ## What to produce

        Rewrite the FS so every accepted resolution is folded into the
        relevant section. Keep the document's original structure and
        tone. Tag each edited section with ``[REFINED]`` so reviewers
        can see what changed. Do not drop pre-existing content unless
        a resolution directly contradicts it.

        ## How to submit

        Call the MCP tool with the full refined markdown:

        ```
        submit_refine(task_id="{task_id}", refined_fs_markdown=<FULL MARKDOWN HERE>)
        ```
        """
    )


# ── Impact ──────────────────────────────────────────────────────────


IMPACT_SCHEMA = textwrap.dedent(
    """\
    {
      "added_sections": [
        {"section_index": <int>, "section_heading": "<string>", "summary": "<string>"}
      ],
      "removed_sections": [
        {"section_index": <int>, "section_heading": "<string>", "summary": "<string>"}
      ],
      "modified_sections": [
        {
          "section_index": <int>,
          "section_heading": "<string>",
          "change_summary": "<string>",
          "impact_level": "LOW|MEDIUM|HIGH"
        }
      ],
      "affected_tasks": [
        {"task_id": "<string>", "reason": "<string>", "impact_level": "LOW|MEDIUM|HIGH"}
      ],
      "overall_impact": "LOW|MEDIUM|HIGH",
      "notes": "<string>"
    }
    """
)


def build_impact_prompt(
    task_id: UUID | str,
    old_fs_text: str,
    new_fs_text: str,
) -> str:
    """Build the prompt for comparing two FS versions and reporting impact."""
    return _header(
        task_id,
        "Impact analysis between two FS versions",
        SUBMIT_TOOL_BY_KIND["impact"],
    ) + textwrap.dedent(
        f"""\
        ## Previous FS version

        ```
        {old_fs_text.strip()}
        ```

        ## New FS version

        ```
        {new_fs_text.strip()}
        ```

        ## What to produce

        Compare the two documents and return one JSON object matching
        **exactly** this schema:

        ```json
        {IMPACT_SCHEMA}
        ```

        Guidance:

        - Section indexes refer to the **new** version unless the
          section is in ``removed_sections`` (in which case they refer
          to the old version).
        - ``impact_level`` must be ``LOW``, ``MEDIUM``, or ``HIGH`` —
          no other values are allowed.
        - ``affected_tasks`` may be an empty list; include it even if
          empty.

        ## How to submit

        Call the MCP tool with the JSON object as a native argument:

        ```
        submit_impact(task_id="{task_id}", impact=<JSON OBJECT ABOVE>)
        ```
        """
    )


# ── Small helper for the UI ─────────────────────────────────────────


def _resolve_backend_url(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    try:
        from app.config import get_settings  # local import to avoid cycles in tests

        return getattr(get_settings(), "BACKEND_SELF_URL", None) or "http://localhost:8000"
    except Exception:  # noqa: BLE001 — config import must never break the prompt path
        return "http://localhost:8000"


def build_mcp_snippet(backend_url: str | None = None) -> str:
    """Return the canonical ``.cursor/mcp.json`` snippet shown in the modal.

    The snippet must be:

    * Valid JSON (no comments) so the user can paste it verbatim into
      ``.cursor/mcp.json``.
    * Aligned with ``GET /api/orchestration/mcp-config`` (same server
      key, same entry-point, same ``BACKEND_URL`` env wiring) so the
      build flow and the cursor-task flow never drift.
    * Self-explanatory about the working directory: the relative
      ``mcp-server/server.py`` path resolves only when Cursor's
      workspace root is the FS Intelligence Platform repo, which is
      why the modal also tells the user to open Cursor on that repo.

    When ``backend_url`` is omitted, we resolve it from
    ``settings.BACKEND_SELF_URL`` so production deployments stay
    pointed at the right host without each caller having to remember.
    """
    resolved = _resolve_backend_url(backend_url)
    config = {
        "mcpServers": {
            MCP_SERVER_NAME: {
                "command": "python",
                "args": ["mcp-server/server.py"],
                "env": {"BACKEND_URL": resolved},
            }
        }
    }
    return json.dumps(config, indent=2) + "\n"


def build_mcp_setup_instructions(backend_url: str | None = None) -> list[str]:
    """Return the ordered checklist the modal renders next to the snippet."""
    resolved = _resolve_backend_url(backend_url)
    return [
        "Open Cursor with the FS Intelligence Platform repository as the workspace "
        "root (the same folder that contains `mcp-server/server.py`).",
        "Save the JSON below as `.cursor/mcp.json` at that workspace root. "
        "Merge it into the existing file if you already have one.",
        "Fully restart Cursor (Quit, then re-open) — MCP servers are only "
        f"registered at startup. Confirm `{MCP_SERVER_NAME}` shows green in the "
        "MCP panel before pasting the prompt.",
        f"The MCP server reaches the platform via BACKEND_URL={resolved}. "
        "Override it in the snippet only if your backend runs elsewhere.",
    ]
