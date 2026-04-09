"""Edge case detection node — identifies missing scenarios in FS sections.

For each section, asks the LLM what edge cases, error states, and boundary
conditions are not covered. Populates state.edge_cases.
"""

import logging
from typing import List

from app.llm import get_llm_client
from app.pipeline.state import EdgeCaseGap, FSAnalysisState, Severity

logger = logging.getLogger(__name__)

# ── Prompt Templates ────────────────────────────────────

EDGE_CASE_SYSTEM_PROMPT = """You are an expert requirements analyst and QA engineer reviewing Functional Specification (FS) documents.

Your task is to identify MISSING EDGE CASES and uncovered scenarios in a given section. Focus on:

1. **Error states**: What happens when things go wrong? (network failure, invalid data, timeouts)
2. **Empty / null inputs**: Behavior when required fields are empty, null, or missing
3. **Permission boundaries**: What happens when unauthorized users attempt actions?
4. **Concurrent operations**: Race conditions, simultaneous edits, parallel processing
5. **Data validation boundaries**: Min/max values, overflow, special characters, Unicode
6. **Resource limits**: What happens at capacity limits (disk full, memory exhaustion, rate limits)?
7. **State transitions**: Invalid state changes, interrupted operations, rollback scenarios
8. **Integration failures**: What if an external API is down, returns unexpected data, or times out?

For each edge case gap found, provide:
- A clear description of the uncovered scenario
- Impact: HIGH (could cause data loss or security breach), MEDIUM (causes degraded user experience), LOW (minor inconvenience)
- A suggested addition: what should be added to the FS to cover this scenario

Return your analysis as a JSON array. If no edge case gaps found, return an empty array [].

Example output format:
```json
[
  {
    "scenario_description": "No behavior defined for when the payment gateway returns a timeout after the user has been charged but before confirmation is received.",
    "impact": "HIGH",
    "suggested_addition": "Add requirement: If payment gateway times out after charge initiation, the system shall retry confirmation up to 3 times, then queue for manual reconciliation and notify the user with a pending status."
  },
  {
    "scenario_description": "No validation specified for the maximum length of the user's name field.",
    "impact": "LOW",
    "suggested_addition": "Add requirement: User name field shall accept 1-100 characters and reject inputs exceeding this range with a clear error message."
  }
]
```

IMPORTANT: Return ONLY a valid JSON array. No markdown, no explanations outside the JSON."""

EDGE_CASE_USER_PROMPT = """Analyze the following FS document section for missing edge cases and uncovered scenarios:

## Section: {heading}

{content}

---
Return a JSON array of edge case gaps. If no gaps are found, return []."""


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

    client = get_llm_client()
    prompt = EDGE_CASE_USER_PROMPT.format(heading=heading, content=content)

    try:
        result = await client.call_llm_json(
            prompt=prompt,
            system=EDGE_CASE_SYSTEM_PROMPT,
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
            section_index, heading, len(gaps),
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
        len(all_edge_cases), len(sections),
    )

    return {
        **state,
        "edge_cases": all_edge_cases,
        "errors": errors,
    }
