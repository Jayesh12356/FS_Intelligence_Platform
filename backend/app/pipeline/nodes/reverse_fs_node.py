"""Reverse FS generation node — generates FS document from codebase (L8).

Multi-step LLM process:
  Step 1: Module-level summaries per file
  Step 2: User flow identification across codebase
  Step 3: FS section generation per flow
  Step 4: Assembly into structured FSDocument format
"""

import logging
from typing import List, Tuple

from app.config import get_settings
from app.llm.client import LLMError
from app.orchestration.pipeline_llm import pipeline_call_llm, pipeline_call_llm_json
from app.pipeline.prompts.reverse import (
    fs_sections as fs_sections_prompt,
)
from app.pipeline.prompts.reverse import (
    module_summary as module_summary_prompt,
)
from app.pipeline.prompts.reverse import (
    user_flows as user_flows_prompt,
)
from app.pipeline.prompts.shared.flags import legacy_prompts_enabled
from app.pipeline.state import ReverseGenState

logger = logging.getLogger(__name__)

# ── Prompt Templates ────────────────────────────────────

MODULE_SUMMARY_SYSTEM = """You are a code archaeologist reverse-engineering a codebase into documentation. Given a source file, produce a precise functional summary that captures WHAT the module does (not HOW it does it internally).

Return a JSON object with exactly these fields:
{
  "module_name": "filename without extension",
  "purpose": "One sentence: the module's single responsibility. Start with a verb (Handles, Manages, Provides, Implements).",
  "key_components": ["list ONLY public/exported functions and classes — omit internal helpers"],
  "dependencies": ["external libraries, APIs, or services this module integrates with — omit standard library"],
  "summary": "2-3 sentences describing: (1) what inputs it accepts, (2) what processing/transformation it performs, (3) what outputs/side effects it produces"
}

PRECISION RULES:
- "purpose" must be ONE sentence, no conjunctions (if you need "and", the module has two purposes — pick the primary one)
- "key_components" should list 3-10 items max — only the functionally significant ones
- "dependencies" means EXTERNAL packages/services, not internal imports
- "summary" must be understandable by someone who has never seen the code

Return ONLY valid JSON. No markdown fences, no prose outside the object."""

MODULE_SUMMARY_USER = """Summarize this source file's functional purpose.

File: {file_path}
Language: {language}
Entities (functions/classes):
{entities}

Code (first 200 lines):
{code_excerpt}

Return a JSON module summary."""

USER_FLOW_SYSTEM = """You are a software architect identifying the distinct user-facing features in a codebase by analyzing module summaries. A "user flow" is a complete end-to-end capability that delivers value to a user or system consumer.

IDENTIFICATION CRITERIA:
- Each flow must have a clear TRIGGER (user action, API call, scheduled job, event)
- Each flow must produce a clear OUTCOME (data displayed, record created, notification sent, file exported)
- A flow spans multiple modules (if only one module is involved, it is likely a utility, not a flow)
- Merge closely related sub-flows into one (e.g., "Create Order" + "Validate Order" = one "Order Processing" flow)

Return a JSON array:
[
  {
    "flow_name": "Concise feature name (2-4 words)",
    "description": "One sentence: who triggers it, what happens, what the outcome is",
    "involved_modules": ["module names that participate in this flow, in execution order"],
    "entry_points": ["the specific function or endpoint where the flow begins"]
  }
]

TARGET: 3-10 flows. Prioritize user-facing features over internal utilities, background jobs, or infrastructure setup.

Return ONLY valid JSON. No markdown fences, no prose outside the array."""

USER_FLOW_USER = """Identify the distinct user-facing features in this codebase based on the module summaries below.

Module summaries:
{module_summaries}

Codebase stats: {primary_language}, {total_files} files, {total_lines} lines.

Return a JSON array of user flows."""

FS_SECTION_SYSTEM = """You are a senior technical writer producing a Functional Specification from code analysis. Write formal, implementation-independent requirements — describe WHAT the system does, not HOW the code works.

MANDATORY STRUCTURE (use these exact headings):

1. Purpose
   One paragraph: what business capability this feature provides and why it exists.

2. Actors
   Bullet list of user roles or system agents that interact with this feature.

3. Preconditions
   Numbered list of conditions that MUST be true before this feature can execute.

4. Functional Requirements
   Numbered list using "The system shall..." language. Each requirement must be:
   - Specific: contains measurable criteria where possible
   - Testable: a QA engineer can verify it with a concrete test
   - Atomic: one behavior per requirement

5. Alternate Flows & Error Handling
   Numbered list of what happens when preconditions fail, inputs are invalid, or dependencies are unavailable.

6. Data Requirements
   Table or list of data entities: name, type, constraints, source/destination.

7. Non-Functional Requirements
   Performance, security, scalability, or availability requirements evident from the code. Use "shall" language with specific thresholds where the code reveals them.

WRITING RULES:
- Use "shall" for mandatory requirements, "should" for recommendations
- NEVER include code snippets, function names, class names, or file paths
- NEVER say "the code does X" — say "the system shall do X"
- Write for a reader who has never seen the codebase
- Be concise: 150-400 words per section

Return plain text with the section headings above. Do NOT wrap in JSON."""

FS_SECTION_USER = """Write a formal Functional Specification section for this feature. Describe WHAT the system does, not how the code works.

Feature: {flow_name}
Description: {flow_description}

Involved components:
{involved_modules}

Component details:
{module_details}

Return a complete FS section using the required structure (Purpose, Actors, Preconditions, Functional Requirements, Alternate Flows, Data Requirements, Non-Functional Requirements)."""


# ── Node Functions ──────────────────────────────────────


async def _generate_module_summaries(
    files: List[dict],
) -> List[dict]:
    """Step 1: Generate module-level summaries for each file."""
    settings = get_settings()
    summaries: List[dict] = []
    max_entities = max(1, settings.REVERSE_MAX_ENTITIES_PER_FILE)
    max_excerpt_chars = max(1500, settings.REVERSE_MAX_CODE_EXCERPT_CHARS)

    for f in files:
        entities = f.get("entities", [])[:max_entities]
        entities_str = (
            "\n".join(
                [
                    f"  - {e.get('entity_type', 'function')}: {e.get('name', '?')} — {e.get('signature', '')}"
                    + (f" [docstring: {e.get('docstring', '')[:100]}]" if e.get("docstring") else " [no docstring]")
                    for e in entities
                ]
            )
            or "  (no entities extracted)"
        )

        code_content = f.get("content", "")
        # Bound excerpt for deterministic token control.
        code_excerpt = code_content[:max_excerpt_chars]
        if len(code_content) > max_excerpt_chars:
            code_excerpt += "\n\n# [truncated]"

        if legacy_prompts_enabled():
            system_prompt = MODULE_SUMMARY_SYSTEM
            user_prompt = MODULE_SUMMARY_USER.format(
                file_path=f.get("path", ""),
                language=f.get("language", ""),
                entities=entities_str,
                code_excerpt=code_excerpt,
            )
        else:
            system_prompt, user_prompt = module_summary_prompt.build(
                file_path=f.get("path", ""),
                language=f.get("language", ""),
                entities=entities_str,
                code_excerpt=code_excerpt,
            )

        try:
            result = await pipeline_call_llm_json(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.0,
                max_tokens=1024,
                role="longcontext",
            )
            if isinstance(result, dict):
                result["file_path"] = f.get("path", "")
                summaries.append(result)
            else:
                summaries.append(
                    {
                        "file_path": f.get("path", ""),
                        "module_name": f.get("path", "").split("/")[-1],
                        "purpose": "Could not analyze",
                        "summary": "Analysis failed",
                        "key_components": [],
                        "dependencies": [],
                    }
                )
        except LLMError:
            raise
        except Exception as exc:
            logger.warning("Module summary failed for %s: %s", f.get("path", "?"), exc)
            summaries.append(
                {
                    "file_path": f.get("path", ""),
                    "module_name": f.get("path", "").split("/")[-1],
                    "purpose": "Analysis failed",
                    "summary": str(exc),
                    "key_components": [],
                    "dependencies": [],
                }
            )

    return summaries


def _select_summary_files(snapshot: dict) -> Tuple[List[dict], List[dict]]:
    """Select initial and fallback file sets for staged reverse generation."""
    settings = get_settings()
    files: List[dict] = snapshot.get("files", [])
    initial_n = max(5, settings.REVERSE_TOP_FILES_INITIAL)
    max_n = max(initial_n, settings.REVERSE_TOP_FILES_MAX)

    candidates = files[:max_n]

    # Deduplicate near-identical files by path/name + entity signature fingerprint.
    seen = set()
    deduped = []
    for f in candidates:
        ents = f.get("entities", [])
        sigs = "|".join(sorted(e.get("name", "") for e in ents[:20]))
        fp = f"{f.get('path', '').split('/')[-1]}::{f.get('line_count', 0)}::{sigs}"
        key = hash(fp)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)

    initial = deduped[:initial_n]
    fallback = deduped[initial_n:max_n]
    return initial, fallback


async def _identify_user_flows(
    summaries: List[dict],
    snapshot: dict,
) -> List[str]:
    """Step 2: Identify main user flows from module summaries."""
    summaries_str = "\n\n".join(
        [
            f"### {s.get('module_name', '?')} ({s.get('file_path', '')})\n"
            f"Purpose: {s.get('purpose', 'unknown')}\n"
            f"Components: {', '.join(s.get('key_components', []))}\n"
            f"Summary: {s.get('summary', '')}"
            for s in summaries
        ]
    )

    if legacy_prompts_enabled():
        system_prompt = USER_FLOW_SYSTEM
        user_prompt = USER_FLOW_USER.format(
            module_summaries=summaries_str,
            primary_language=snapshot.get("primary_language", ""),
            total_files=snapshot.get("total_files", 0),
            total_lines=snapshot.get("total_lines", 0),
        )
    else:
        system_prompt, user_prompt = user_flows_prompt.build(
            module_summaries=summaries_str,
            primary_language=snapshot.get("primary_language", ""),
            total_files=snapshot.get("total_files", 0),
            total_lines=snapshot.get("total_lines", 0),
        )

    try:
        result = await pipeline_call_llm_json(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.0,
            max_tokens=4096,
            role="longcontext",
        )
        if isinstance(result, list):
            return result
        return []
    except LLMError:
        raise
    except Exception as exc:
        logger.error("User flow identification failed: %s", exc)
        return []


async def _generate_fs_sections(
    flows: List[dict],
    summaries: List[dict],
) -> List[dict]:
    """Step 3: Generate FS sections for each identified flow."""
    sections: List[dict] = []

    # Build module lookup
    module_by_name: dict[str, dict] = {}
    for s in summaries:
        module_by_name[s.get("module_name", "")] = s
        module_by_name[s.get("file_path", "")] = s

    for i, flow in enumerate(flows):
        flow_name = flow.get("flow_name", f"Feature {i + 1}")
        flow_desc = flow.get("description", "")
        involved = flow.get("involved_modules", [])

        # Gather module details for this flow
        module_details_parts = []
        for mod_name in involved:
            mod = module_by_name.get(mod_name)
            if mod:
                module_details_parts.append(
                    f"**{mod.get('module_name', mod_name)}**\n"
                    f"  Purpose: {mod.get('purpose', '?')}\n"
                    f"  Components: {', '.join(mod.get('key_components', []))}\n"
                    f"  {mod.get('summary', '')}"
                )
            else:
                module_details_parts.append(f"**{mod_name}** — (no details available)")

        module_details_str = "\n\n".join(module_details_parts) or "(no module details)"
        involved_str = "\n".join([f"- {m}" for m in involved]) or "- (none identified)"

        if legacy_prompts_enabled():
            system_prompt = FS_SECTION_SYSTEM
            user_prompt = FS_SECTION_USER.format(
                flow_name=flow_name,
                flow_description=flow_desc,
                involved_modules=involved_str,
                module_details=module_details_str,
            )
        else:
            system_prompt, user_prompt = fs_sections_prompt.build(
                flow_name=flow_name,
                flow_description=flow_desc,
                involved_modules=involved_str,
                module_details=module_details_str,
            )

        try:
            result = await pipeline_call_llm(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.1,
                max_tokens=4096,
                role="longcontext",
            )
            sections.append(
                {
                    "heading": flow_name,
                    "content": result.strip(),
                    "section_index": i,
                }
            )
        except LLMError:
            raise
        except Exception as exc:
            logger.error("FS section generation failed for flow '%s': %s", flow_name, exc)
            sections.append(
                {
                    "heading": flow_name,
                    "content": f"[Generation failed: {exc}]",
                    "section_index": i,
                }
            )

    return sections


def _assemble_fs_text(sections: List[dict]) -> str:
    """Step 4: Assemble sections into a coherent FS document."""
    parts = [
        "# Generated Functional Specification",
        "",
        "This document was automatically generated from source code analysis.",
        "It describes the functional requirements inferred from the implementation.",
        "",
        "---",
        "",
    ]

    for section in sections:
        heading = section.get("heading", "Untitled")
        content = section.get("content", "")
        parts.append(f"## {heading}")
        parts.append("")
        parts.append(content)
        parts.append("")
        parts.append("---")
        parts.append("")

    return "\n".join(parts)


# ── LangGraph Node Function ─────────────────────────────


async def reverse_fs_node(state: ReverseGenState) -> ReverseGenState:
    """LangGraph node: generate FS document from codebase snapshot.

    Multi-step process:
      1. Module-level summaries per file
      2. User flow identification
      3. FS section generation per flow
      4. Assembly into structured document
    """
    snapshot = state.get("snapshot", {})
    errors: List[str] = list(state.get("errors", []))

    logger.info(
        "Reverse FS node: generating from %d files for upload=%s",
        snapshot.get("total_files", 0),
        state.get("code_upload_id", "?"),
    )

    try:
        initial_files, fallback_files = _select_summary_files(snapshot)
        generation_stats = {
            "snapshot_files_total": len(snapshot.get("files", [])),
            "initial_summary_files": len(initial_files),
            "fallback_summary_files": len(fallback_files),
            "used_fallback_pass": False,
            "module_summary_calls": 0,
            "flow_calls": 0,
            "section_generation_calls": 0,
        }

        # Step 1: Module summaries
        logger.info("Step 1/4: Generating module summaries...")
        module_summaries = await _generate_module_summaries(initial_files)
        generation_stats["module_summary_calls"] += len(initial_files)
        logger.info("Generated %d module summaries", len(module_summaries))

        # Step 2: User flow identification
        logger.info("Step 2/4: Identifying user flows...")
        user_flows = await _identify_user_flows(module_summaries, snapshot)
        generation_stats["flow_calls"] += 1
        logger.info("Identified %d user flows", len(user_flows))

        # Optional second pass: expand context if flow coverage is too shallow.
        min_flows = max(1, get_settings().REVERSE_MIN_ACCEPTABLE_FLOWS)
        if len(user_flows) < min_flows and fallback_files:
            logger.info(
                "Flow count %d is below threshold %d; running expanded summary pass",
                len(user_flows),
                min_flows,
            )
            extra_summaries = await _generate_module_summaries(fallback_files)
            generation_stats["module_summary_calls"] += len(fallback_files)
            module_summaries.extend(extra_summaries)
            user_flows = await _identify_user_flows(module_summaries, snapshot)
            generation_stats["flow_calls"] += 1
            generation_stats["used_fallback_pass"] = True

        # Step 3: FS section generation
        logger.info("Step 3/4: Generating FS sections...")
        generated_sections = await _generate_fs_sections(user_flows, module_summaries)
        generation_stats["section_generation_calls"] = len(user_flows)
        logger.info("Generated %d FS sections", len(generated_sections))

        # Step 4: Assembly
        logger.info("Step 4/4: Assembling FS document...")
        raw_fs_text = _assemble_fs_text(generated_sections)

    except Exception as exc:
        error_msg = f"Reverse FS generation failed: {exc}"
        logger.error(error_msg)
        errors.append(error_msg)
        generation_stats = {}
        module_summaries = []
        user_flows = []
        generated_sections = []
        raw_fs_text = ""

    flow_names = [f.get("flow_name", "?") if isinstance(f, dict) else str(f) for f in user_flows]

    return {
        **state,
        "module_summaries": module_summaries,
        "user_flows": flow_names,
        "generated_sections": generated_sections,
        "raw_fs_text": raw_fs_text,
        "generation_stats": generation_stats,
        "errors": errors,
    }
