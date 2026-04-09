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

CONTRADICTION_SYSTEM_PROMPT = """You are an expert requirements analyst for enterprise Functional Specification (FS) documents.

Your task is to identify CONTRADICTIONS between two sections of an FS document. A contradiction exists when:

1. **Direct conflict**: Two sections make opposing statements (e.g., one says "data is retained for 30 days", another says "data is deleted after 7 days")
2. **Logical inconsistency**: Requirements that cannot both be satisfied simultaneously
3. **Behavioral conflict**: Different expected behaviors for the same scenario
4. **Scope conflict**: One section includes something another section explicitly excludes
5. **Temporal conflict**: Different timelines or deadlines for dependent processes

For each contradiction found, provide:
- A clear description of the conflict
- Severity: HIGH (blocks development — impossible to implement both), MEDIUM (causes confusion — ambiguous priority), LOW (minor inconsistency — can be resolved with clarification)
- A suggested resolution: which section to trust, or how to reconcile

Return your analysis as a JSON array. If no contradictions found, return an empty array [].

Example output format:
```json
[
  {
    "description": "Section A states data must be retained for 90 days, but Section B requires immediate deletion after processing.",
    "severity": "HIGH",
    "suggested_resolution": "Clarify with the compliance team. Section B likely refers to temporary processing data, while Section A covers audit logs. Add explicit scope to each policy."
  }
]
```

IMPORTANT: Return ONLY a valid JSON array. No markdown, no explanations outside the JSON."""

CONTRADICTION_USER_PROMPT = """Compare these two FS document sections for contradictions:

## Section A: {heading_a} (Section {index_a})

{content_a}

---

## Section B: {heading_b} (Section {index_b})

{content_b}

---
Return a JSON array of contradictions. If no contradictions are found, return []."""


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
