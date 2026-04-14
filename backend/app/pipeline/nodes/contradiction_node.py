"""Contradiction detection node — finds conflicting requirements between sections.

For each pair of sections, asks the LLM whether the requirements contradict
each other. Populates state.contradictions with Contradiction objects.
"""

import logging
from itertools import combinations
from typing import List

from app.llm import get_llm_client
from app.pipeline.state import Contradiction, FSAnalysisState, Severity

logger = logging.getLogger(__name__)

# ── Prompt Templates ────────────────────────────────────

CONTRADICTION_SYSTEM_PROMPT = """You are a principal requirements analyst specializing in cross-reference validation of Functional Specifications. You detect requirements that CANNOT both be implemented as written — contradictions that force a developer to choose one requirement over another.

TASK: Compare two FS sections and identify requirements that are MUTUALLY EXCLUSIVE or LOGICALLY INCOMPATIBLE. A contradiction means a developer CANNOT satisfy both sections simultaneously.

WHAT COUNTS AS A CONTRADICTION:
1. NUMERIC CONFLICT — Section A specifies a value (retention period, timeout, limit) that directly conflicts with a value in Section B for the same entity.
2. BEHAVIORAL CONFLICT — Same trigger/event produces different required outcomes in each section.
3. LOGICAL IMPOSSIBILITY — Satisfying requirement A makes it physically/logically impossible to satisfy requirement B.
4. SCOPE CONFLICT — Section A explicitly includes what Section B explicitly excludes (or vice versa) for the same feature.
5. SEQUENCE CONFLICT — Section A requires X before Y; Section B requires Y before X.

WHAT IS NOT A CONTRADICTION:
- Sections describing DIFFERENT features that happen to use similar terminology
- General statements in one section with specific overrides in another (this is normal FS layering)
- Complementary requirements that cover different aspects of the same feature
- One section adding detail that the other section omits (this is elaboration, not conflict)

SEVERITY CALIBRATION:
- HIGH: Both requirements use mandatory language (shall/must) and cannot coexist. A developer must violate one to satisfy the other. Blocks implementation.
- MEDIUM: Requirements appear to conflict but COULD be reconciled with a reasonable interpretation. Needs clarification to avoid incorrect implementation.
- LOW: Minor tension between sections that an experienced architect can resolve with standard patterns. Low risk of build error.

OUTPUT RULES:
- "description" must quote the specific conflicting text from BOTH sections
- "suggested_resolution" must propose a concrete reconciliation (not just "clarify with the team")

Return a JSON array. Empty array [] if no contradictions exist.

Example:
[
  {
    "description": "Section A requires 'User data shall be retained for 90 days after account deletion' but Section B states 'All personal data must be permanently deleted within 7 days of a deletion request.' Both use mandatory language for the same data with incompatible timelines.",
    "severity": "HIGH",
    "suggested_resolution": "Separate data categories: personal/PII data follows the 7-day deletion policy (Section B), while anonymized usage logs follow the 90-day retention policy (Section A). Add explicit data classification to both sections."
  }
]

Return ONLY a valid JSON array. No markdown fences, no prose outside the array."""

CONTRADICTION_USER_PROMPT = """Determine whether these two sections contain requirements that CANNOT both be implemented as written. Only flag genuine conflicts — not elaborations, not complementary details.

SECTION A: "{heading_a}" (Section {index_a})
{content_a}

SECTION B: "{heading_b}" (Section {index_b})
{content_b}

Return a JSON array of contradictions. If both sections are compatible, return []."""


# ── Detection Function ──────────────────────────────────


async def detect_contradictions_between_sections(
    heading_a: str,
    content_a: str,
    index_a: int,
    heading_b: str,
    content_b: str,
    index_b: int,
) -> List[Contradiction]:
    """Detect contradictions between two FS sections using the LLM.

    Args:
        heading_a: Heading of the first section.
        content_a: Content of the first section.
        index_a: Section index of the first section.
        heading_b: Heading of the second section.
        content_b: Content of the second section.
        index_b: Section index of the second section.

    Returns:
        List of Contradiction objects found between the sections.
    """
    # Skip trivially short sections
    if len(content_a.strip()) < 20 or len(content_b.strip()) < 20:
        return []

    client = get_llm_client()
    prompt = CONTRADICTION_USER_PROMPT.format(
        heading_a=heading_a,
        content_a=content_a,
        index_a=index_a + 1,
        heading_b=heading_b,
        content_b=content_b,
        index_b=index_b + 1,
    )

    try:
        result = await client.call_llm_json(
            prompt=prompt,
            system=CONTRADICTION_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=2048,
            role="reasoning",
        )

        if not isinstance(result, list):
            logger.warning(
                "LLM returned non-list for contradiction check (%s vs %s): %s",
                heading_a, heading_b, type(result),
            )
            return []

        contradictions: List[Contradiction] = []
        for item in result:
            try:
                severity_str = item.get("severity", "MEDIUM").upper()
                severity = Severity(severity_str) if severity_str in Severity.__members__ else Severity.MEDIUM

                contradiction = Contradiction(
                    section_a_index=index_a,
                    section_a_heading=heading_a,
                    section_b_index=index_b,
                    section_b_heading=heading_b,
                    description=item.get("description", ""),
                    severity=severity,
                    suggested_resolution=item.get("suggested_resolution", ""),
                )
                contradictions.append(contradiction)
            except Exception as exc:
                logger.warning("Failed to parse contradiction: %s — %s", item, exc)

        logger.info(
            "Contradiction check (%s vs %s): found %d",
            heading_a, heading_b, len(contradictions),
        )
        return contradictions

    except Exception as exc:
        logger.error(
            "Contradiction detection failed (%s vs %s): %s",
            heading_a, heading_b, exc,
        )
        return []


# ── LangGraph Node Function ─────────────────────────────


async def contradiction_node(state: FSAnalysisState) -> FSAnalysisState:
    """LangGraph node: detect contradictions across all section pairs.

    Reads state.parsed_sections, compares each unique pair,
    and populates state.contradictions with the results.
    """
    sections = state.get("parsed_sections", [])
    all_contradictions: List[dict] = []
    errors: List[str] = list(state.get("errors", []))

    logger.info(
        "Contradiction node: analyzing %d sections (%d pairs) for fs_id=%s",
        len(sections),
        len(sections) * (len(sections) - 1) // 2,
        state.get("fs_id", "?"),
    )

    # Compare each unique pair of sections
    for sec_a, sec_b in combinations(sections, 2):
        heading_a = sec_a.get("heading", "Untitled")
        content_a = sec_a.get("content", "")
        index_a = sec_a.get("section_index", 0)
        heading_b = sec_b.get("heading", "Untitled")
        content_b = sec_b.get("content", "")
        index_b = sec_b.get("section_index", 0)

        try:
            found = await detect_contradictions_between_sections(
                heading_a, content_a, index_a,
                heading_b, content_b, index_b,
            )
            for c in found:
                all_contradictions.append(c.model_dump())
        except Exception as exc:
            error_msg = f"Contradiction detection failed ({index_a} vs {index_b}): {exc}"
            logger.error(error_msg)
            errors.append(error_msg)

    logger.info(
        "Contradiction node complete: %d contradictions across %d sections",
        len(all_contradictions), len(sections),
    )

    return {
        **state,
        "contradictions": all_contradictions,
        "errors": errors,
    }
