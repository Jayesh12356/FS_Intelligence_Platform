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
from app.llm import get_llm_client
from app.pipeline.state import ReverseGenState

logger = logging.getLogger(__name__)

# ── Prompt Templates ────────────────────────────────────

MODULE_SUMMARY_SYSTEM = """You are an expert code analyst. Given a source code file with its functions and classes, write a clear, concise summary of what this module does.

Focus on:
- The primary purpose of this module
- Key classes and their responsibilities
- Important functions and what they do
- Any external dependencies or APIs used

Return a JSON object:
{
  "module_name": "filename without extension",
  "purpose": "One sentence describing the module's purpose",
  "key_components": ["list of important functions/classes"],
  "dependencies": ["external libraries or APIs used"],
  "summary": "2-3 sentence detailed description"
}

IMPORTANT: Return ONLY valid JSON. No markdown, no explanations."""

MODULE_SUMMARY_USER = """Analyze this source file:

**File**: {file_path}
**Language**: {language}
**Entities**:
{entities}

**Code excerpt** (first 200 lines):
{code_excerpt}

Provide a module-level summary."""

USER_FLOW_SYSTEM = """You are an expert at understanding software architectures. Given summaries of all modules in a codebase, identify the main user-facing flows or features.

A "user flow" is a complete feature or capability of the system (e.g., "User Authentication", "Order Processing", "Report Generation").

Return a JSON array of flow objects:
[
  {
    "flow_name": "Name of the flow/feature",
    "description": "What this flow does from a user/system perspective",
    "involved_modules": ["list of module names involved"],
    "entry_points": ["where the flow starts"]
  }
]

Identify 3-10 flows. Focus on major features, not internal utilities.

IMPORTANT: Return ONLY valid JSON. No markdown, no explanations."""

USER_FLOW_USER = """Here are the module summaries for the codebase:

{module_summaries}

Primary language: {primary_language}
Total files: {total_files}
Total lines: {total_lines}

Identify the main user-facing flows and features in this system."""

FS_SECTION_SYSTEM = """You are a senior technical writer generating a Functional Specification (FS) document from code analysis.

For the given user flow, write a formal FS section that describes:
1. **Purpose**: What this feature does
2. **Actors**: Who uses this feature
3. **Preconditions**: What must be true before this feature can be used
4. **Main Flow**: Step-by-step description of the happy path
5. **Alternate Flows**: Edge cases and error handling
6. **Data Requirements**: What data is needed/produced
7. **Non-Functional Requirements**: Performance, security, etc. (if evident from code)

Write in clear, professional requirements language. Use "shall" for requirements.
Do NOT include code snippets — this is a functional specification, not technical docs.

Return the section as plain text with clear headings. Do not wrap in JSON."""

FS_SECTION_USER = """Generate an FS section for this flow:

**Flow**: {flow_name}
**Description**: {flow_description}

**Involved Modules**:
{involved_modules}

**Module Details**:
{module_details}

Write a complete FS section for this flow."""


# ── Node Functions ──────────────────────────────────────


async def _generate_module_summaries(
    files: List[dict],
) -> List[dict]:
    """Step 1: Generate module-level summaries for each file."""
    client = get_llm_client()
    settings = get_settings()
    summaries: List[dict] = []
    max_entities = max(1, settings.REVERSE_MAX_ENTITIES_PER_FILE)
    max_excerpt_chars = max(1500, settings.REVERSE_MAX_CODE_EXCERPT_CHARS)

    for f in files:
        entities = f.get("entities", [])[:max_entities]
        entities_str = "\n".join([
            f"  - {e.get('entity_type', 'function')}: {e.get('name', '?')} — {e.get('signature', '')}"
            + (f" [docstring: {e.get('docstring', '')[:100]}]" if e.get('docstring') else " [no docstring]")
            for e in entities
        ]) or "  (no entities extracted)"

        code_content = f.get("content", "")
        # Bound excerpt for deterministic token control.
        code_excerpt = code_content[:max_excerpt_chars]
        if len(code_content) > max_excerpt_chars:
            code_excerpt += "\n\n# [truncated]"

        prompt = MODULE_SUMMARY_USER.format(
            file_path=f.get("path", ""),
            language=f.get("language", ""),
            entities=entities_str,
            code_excerpt=code_excerpt,
        )

        try:
            result = await client.call_llm_json(
                prompt=prompt,
                system=MODULE_SUMMARY_SYSTEM,
                temperature=0.0,
                max_tokens=1024,
            )
            if isinstance(result, dict):
                result["file_path"] = f.get("path", "")
                summaries.append(result)
            else:
                summaries.append({
                    "file_path": f.get("path", ""),
                    "module_name": f.get("path", "").split("/")[-1],
                    "purpose": "Could not analyze",
                    "summary": "Analysis failed",
                    "key_components": [],
                    "dependencies": [],
                })
        except Exception as exc:
            logger.warning("Module summary failed for %s: %s", f.get("path", "?"), exc)
            summaries.append({
                "file_path": f.get("path", ""),
                "module_name": f.get("path", "").split("/")[-1],
                "purpose": "Analysis failed",
                "summary": str(exc),
                "key_components": [],
                "dependencies": [],
            })

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
        sigs = "|".join(sorted((e.get("name", "") for e in ents[:20])))
        fp = f"{f.get('path','').split('/')[-1]}::{f.get('line_count',0)}::{sigs}"
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
    client = get_llm_client()

    summaries_str = "\n\n".join([
        f"### {s.get('module_name', '?')} ({s.get('file_path', '')})\n"
        f"Purpose: {s.get('purpose', 'unknown')}\n"
        f"Components: {', '.join(s.get('key_components', []))}\n"
        f"Summary: {s.get('summary', '')}"
        for s in summaries
    ])

    prompt = USER_FLOW_USER.format(
        module_summaries=summaries_str,
        primary_language=snapshot.get("primary_language", ""),
        total_files=snapshot.get("total_files", 0),
        total_lines=snapshot.get("total_lines", 0),
    )

    try:
        result = await client.call_llm_json(
            prompt=prompt,
            system=USER_FLOW_SYSTEM,
            temperature=0.0,
            max_tokens=4096,
        )
        if isinstance(result, list):
            return result
        return []
    except Exception as exc:
        logger.error("User flow identification failed: %s", exc)
        return []


async def _generate_fs_sections(
    flows: List[dict],
    summaries: List[dict],
) -> List[dict]:
    """Step 3: Generate FS sections for each identified flow."""
    client = get_llm_client()
    sections: List[dict] = []

    # Build module lookup
    module_by_name: dict[str, dict] = {}
    for s in summaries:
        module_by_name[s.get("module_name", "")] = s
        module_by_name[s.get("file_path", "")] = s

    for i, flow in enumerate(flows):
        flow_name = flow.get("flow_name", f"Feature {i+1}")
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

        prompt = FS_SECTION_USER.format(
            flow_name=flow_name,
            flow_description=flow_desc,
            involved_modules=involved_str,
            module_details=module_details_str,
        )

        try:
            result = await client.call_llm(
                prompt=prompt,
                system=FS_SECTION_SYSTEM,
                temperature=0.1,
                max_tokens=4096,
            )
            sections.append({
                "heading": flow_name,
                "content": result.strip(),
                "section_index": i,
            })
        except Exception as exc:
            logger.error("FS section generation failed for flow '%s': %s", flow_name, exc)
            sections.append({
                "heading": flow_name,
                "content": f"[Generation failed: {exc}]",
                "section_index": i,
            })

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
