"""Edge case detection node — identifies missing scenarios in FS sections.

For each section, asks the LLM what edge cases, error states, and boundary
conditions are not covered. Populates state.edge_cases.
"""

import logging
from typing import List

from app.orchestration.pipeline_llm import pipeline_call_llm_json
from app.pipeline.prompts.analysis import edge_case as edge_case_prompt
from app.pipeline.prompts.shared.flags import legacy_prompts_enabled
from app.pipeline.state import EdgeCaseGap, FSAnalysisState, Severity

logger = logging.getLogger(__name__)

# ── Prompt Templates ────────────────────────────────────

EDGE_CASE_SYSTEM_PROMPT = """You are a senior QA architect who writes test plans for mission-critical enterprise systems. You find the scenarios that cause production incidents — the cases the FS author forgot to specify.

TASK: Read the FS section and identify scenarios where the specification is SILENT — where a real user or system event would occur but the FS does not define what the system should do. Only flag gaps that are ACTUALLY MISSING from the text — do not flag scenarios already covered.

DETECTION CATEGORIES (apply only those relevant to the section's domain):

1. FAILURE PATHS — The FS describes the happy path but not: network timeout, service unavailable, partial failure, corrupted input, disk full, rate limit exceeded.
2. BOUNDARY CONDITIONS — The FS mentions a field or value but not: minimum, maximum, empty, null, zero, negative, overflow, special characters, Unicode, extremely long input.
3. AUTHORIZATION GAPS — The FS describes an action but not: what happens when an unauthorized user attempts it, when a session expires mid-operation, when permissions change during execution.
4. CONCURRENCY — The FS describes operations but not: two users editing the same record simultaneously, duplicate form submissions, race conditions between dependent operations.
5. STATE MACHINE GAPS — The FS describes states but not: invalid transitions, interrupted operations (browser closed mid-save, network drops mid-transaction), rollback behavior.
6. DATA INTEGRITY — The FS describes data operations but not: referential integrity on deletion, orphaned records, data migration from legacy state.
7. INTEGRATION BOUNDARIES — The FS references external systems but not: what happens when they return unexpected formats, when they are deprecated, when response schemas change.

IMPACT CALIBRATION:
- HIGH: Could cause data loss, financial discrepancy, security breach, or system crash in production. MUST be addressed before implementation.
- MEDIUM: Causes user confusion, degraded experience, or requires manual intervention. Should be addressed.
- LOW: Minor inconvenience with a reasonable default behavior. Nice to specify but not blocking.

PRECISION RULES:
- Each gap must be SPECIFIC to this section's content — not generic best practices
- "suggested_addition" must be a COMPLETE, implementable requirement (use "shall" language, include specific numbers/behaviors)
- Do NOT suggest additions for scenarios already covered elsewhere in the section
- Limit output to the 3-7 MOST impactful gaps — quality over quantity

Return a JSON array. Empty array [] if the section thoroughly covers all relevant scenarios.

Example:
[
  {
    "scenario_description": "The section specifies payment processing via the gateway but does not define behavior when the gateway returns a timeout AFTER the charge has been initiated but BEFORE confirmation is received. This creates a potential double-charge or lost-payment scenario.",
    "impact": "HIGH",
    "suggested_addition": "The system shall implement idempotent payment processing. If the payment gateway does not respond within 30 seconds after charge initiation, the system shall: (1) retry the confirmation request up to 3 times with exponential backoff, (2) if still unconfirmed, queue the transaction for manual reconciliation, (3) display a 'Payment Pending' status to the user, and (4) send an email notification within 5 minutes."
  }
]

Return ONLY a valid JSON array. No markdown fences, no prose outside the array."""

EDGE_CASE_USER_PROMPT = """Read this FS section carefully. For every requirement, ask: "What happens when this goes wrong, gets unexpected input, or encounters a boundary condition?" Flag only scenarios the section is genuinely silent on.

Section: "{heading}"

{content}

Return a JSON array of the most impactful missing edge cases. If the section thoroughly covers failure paths and boundaries, return []."""


# ── Detection Function ──────────────────────────────────


async def detect_edge_cases_in_section(
    heading: str,
    content: str,
    section_index: int,
) -> List[EdgeCaseGap]:
    """Detect edge case gaps in a single FS section using the LLM.

    Args:
        heading: Section heading text.
        content: Section body text.
        section_index: Index of the section in the document.

    Returns:
        List of EdgeCaseGap objects found in this section.
    """
    if not content or len(content.strip()) < 20:
        logger.debug("Skipping section %d (%s): too short for edge case analysis", section_index, heading)
        return []

    if legacy_prompts_enabled():
        system = EDGE_CASE_SYSTEM_PROMPT
        prompt = EDGE_CASE_USER_PROMPT.format(heading=heading, content=content)
    else:
        system, prompt = edge_case_prompt.build(heading, content)

    try:
        result = await pipeline_call_llm_json(
            prompt=prompt,
            system=system,
            temperature=0.0,
            max_tokens=2048,
        )

        if not isinstance(result, list):
            logger.warning("LLM returned non-list for edge cases in section %d: %s", section_index, type(result))
            return []

        gaps: List[EdgeCaseGap] = []
        for item in result:
            try:
                impact_str = item.get("impact", "MEDIUM").upper()
                impact = Severity(impact_str) if impact_str in Severity.__members__ else Severity.MEDIUM

                gap = EdgeCaseGap(
                    section_index=section_index,
                    section_heading=heading,
                    scenario_description=item.get("scenario_description", ""),
                    impact=impact,
                    suggested_addition=item.get("suggested_addition", ""),
                )
                gaps.append(gap)
            except Exception as exc:
                logger.warning("Failed to parse edge case gap: %s — %s", item, exc)

        logger.info(
            "Section %d (%s): found %d edge case gaps",
            section_index,
            heading,
            len(gaps),
        )
        return gaps

    except Exception as exc:
        logger.error("Edge case detection failed for section %d: %s", section_index, exc)
        return []


# ── LangGraph Node Function ─────────────────────────────


async def edge_case_node(state: FSAnalysisState) -> FSAnalysisState:
    """LangGraph node: detect edge case gaps across all parsed sections.

    Reads state.parsed_sections, runs edge case detection on each,
    and populates state.edge_cases with the results.
    """
    sections = state.get("parsed_sections", [])
    all_edge_cases: List[dict] = []
    errors: List[str] = list(state.get("errors", []))

    logger.info("Edge case node: analyzing %d sections for fs_id=%s", len(sections), state.get("fs_id", "?"))

    for section in sections:
        heading = section.get("heading", "Untitled")
        content = section.get("content", "")
        section_index = section.get("section_index", 0)

        try:
            gaps = await detect_edge_cases_in_section(heading, content, section_index)
            for gap in gaps:
                all_edge_cases.append(gap.model_dump())
        except Exception as exc:
            error_msg = f"Edge case detection failed for section {section_index}: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)

    logger.info(
        "Edge case node complete: %d gaps across %d sections",
        len(all_edge_cases),
        len(sections),
    )

    return {
        **state,
        "edge_cases": all_edge_cases,
        "errors": errors,
    }
