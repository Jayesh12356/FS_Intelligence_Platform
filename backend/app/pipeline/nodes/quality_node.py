"""Quality scoring node — computes overall FS quality score with compliance tagging.

Reads ambiguities, contradictions, and edge cases from the pipeline state
to compute sub-scores and an overall quality grade. Also uses LLM to detect
compliance-relevant sections (payments, auth, PII, external APIs).
"""

import logging
from typing import List

from app.llm import get_llm_client
from app.pipeline.state import (
    ComplianceTag,
    FSAnalysisState,
    FSQualityScore,
    Severity,
)

logger = logging.getLogger(__name__)

# ── Compliance Detection Prompt ─────────────────────────

COMPLIANCE_SYSTEM_PROMPT = """You are an expert compliance analyst reviewing Functional Specification (FS) documents.

Your task is to identify sections that involve compliance-relevant areas. Tag sections that mention or involve:

1. **payments** — Payment processing, billing, charges, refunds, financial transactions
2. **auth** — Authentication, authorization, access control, login, sessions, tokens, roles
3. **pii** — Personally Identifiable Information: names, emails, phone numbers, addresses, SSNs, health data
4. **external_api** — Integration with external/third-party APIs, webhooks, external services
5. **security** — Encryption, data protection, vulnerability handling, SSL/TLS, firewall rules
6. **data_retention** — Data storage duration, deletion policies, archival, backup procedures

For each compliance tag, provide:
- The tag category (one of: payments, auth, pii, external_api, security, data_retention)
- A brief reason explaining why this section is tagged

Return your analysis as a JSON array. If no compliance areas detected, return an empty array [].

Example output format:
```json
[
  {
    "tag": "payments",
    "reason": "Section describes payment gateway integration and refund processing logic."
  },
  {
    "tag": "pii",
    "reason": "Section references user email addresses and phone numbers for notifications."
  }
]
```

IMPORTANT: Return ONLY a valid JSON array. No markdown, no explanations outside the JSON."""

COMPLIANCE_USER_PROMPT = """Analyze the following FS document section for compliance-relevant areas:

## Section: {heading}

{content}

---
Return a JSON array of compliance tags. If no compliance areas detected, return []."""

# Valid compliance tag values
VALID_TAGS = {"payments", "auth", "pii", "external_api", "security", "data_retention"}

# Quality score weights
WEIGHT_COMPLETENESS = 0.35
WEIGHT_CLARITY = 0.35
WEIGHT_CONSISTENCY = 0.30


# ── Compliance Detection Function ───────────────────────


async def detect_compliance_tags_in_section(
    heading: str,
    content: str,
    section_index: int,
) -> List[ComplianceTag]:
    """Detect compliance-relevant tags in a single FS section.

    Args:
        heading: Section heading text.
        content: Section body text.
        section_index: Index of the section in the document.

    Returns:
        List of ComplianceTag objects found in this section.
    """
    if not content or len(content.strip()) < 20:
        return []

    client = get_llm_client()
    prompt = COMPLIANCE_USER_PROMPT.format(heading=heading, content=content)

    try:
        result = await client.call_llm_json(
            prompt=prompt,
            system=COMPLIANCE_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=1024,
        )

        if not isinstance(result, list):
            logger.warning("LLM returned non-list for compliance in section %d: %s", section_index, type(result))
            return []

        tags: List[ComplianceTag] = []
        for item in result:
            try:
                tag_value = item.get("tag", "").lower().strip()
                if tag_value not in VALID_TAGS:
                    logger.warning("Invalid compliance tag '%s' — skipping", tag_value)
                    continue

                tag = ComplianceTag(
                    section_index=section_index,
                    section_heading=heading,
                    tag=tag_value,
                    reason=item.get("reason", ""),
                )
                tags.append(tag)
            except Exception as exc:
                logger.warning("Failed to parse compliance tag: %s — %s", item, exc)

        logger.info("Section %d (%s): found %d compliance tags", section_index, heading, len(tags))
        return tags

    except Exception as exc:
        logger.error("Compliance detection failed for section %d: %s", section_index, exc)
        return []


# ── Quality Score Computation ───────────────────────────


def compute_quality_score(
    total_sections: int,
    ambiguities: List[dict],
    contradictions: List[dict],
    edge_cases: List[dict],
) -> FSQualityScore:
    """Compute the FS quality score from analysis results.

    Sub-scores:
      - completeness: % of sections with no edge case gaps
      - clarity: % of sections with no ambiguities
      - consistency: 1 - (contradiction_count / max_possible_contradictions)
      - overall: weighted average

    Args:
        total_sections: Number of sections in the document.
        ambiguities: List of ambiguity flag dicts from the pipeline.
        contradictions: List of contradiction dicts from the pipeline.
        edge_cases: List of edge case gap dicts from the pipeline.

    Returns:
        FSQualityScore with all sub-scores and overall.
    """
    if total_sections == 0:
        return FSQualityScore(
            completeness=100.0,
            clarity=100.0,
            consistency=100.0,
            overall=100.0,
        )

    # Clarity: % of sections without ambiguities
    sections_with_ambiguities = set()
    for amb in ambiguities:
        sections_with_ambiguities.add(amb.get("section_index", -1))
    clarity = ((total_sections - len(sections_with_ambiguities)) / total_sections) * 100.0

    # Completeness: % of sections without edge case gaps
    sections_with_gaps = set()
    for gap in edge_cases:
        sections_with_gaps.add(gap.get("section_index", -1))
    completeness = ((total_sections - len(sections_with_gaps)) / total_sections) * 100.0

    # Consistency: based on contradiction rate
    max_pairs = total_sections * (total_sections - 1) / 2 if total_sections > 1 else 1
    contradiction_rate = len(contradictions) / max_pairs if max_pairs > 0 else 0
    consistency = max(0.0, (1.0 - contradiction_rate) * 100.0)

    # Overall weighted average
    overall = (
        WEIGHT_COMPLETENESS * completeness
        + WEIGHT_CLARITY * clarity
        + WEIGHT_CONSISTENCY * consistency
    )

    return FSQualityScore(
        completeness=round(completeness, 1),
        clarity=round(clarity, 1),
        consistency=round(consistency, 1),
        overall=round(overall, 1),
    )


# ── LangGraph Node Function ─────────────────────────────


async def quality_node(state: FSAnalysisState) -> FSAnalysisState:
    """LangGraph node: compute quality scores and detect compliance tags.

    Reads ambiguities, contradictions, and edge_cases from state.
    Computes FSQualityScore and detects compliance tags for each section.
    """
    sections = state.get("parsed_sections", [])
    ambiguities = state.get("ambiguities", [])
    contradictions = state.get("contradictions", [])
    edge_cases = state.get("edge_cases", [])
    errors: List[str] = list(state.get("errors", []))

    logger.info("Quality node: scoring %d sections for fs_id=%s", len(sections), state.get("fs_id", "?"))

    # Compute quality score
    quality = compute_quality_score(
        total_sections=len(sections),
        ambiguities=ambiguities,
        contradictions=contradictions,
        edge_cases=edge_cases,
    )

    logger.info(
        "Quality score: completeness=%.1f, clarity=%.1f, consistency=%.1f, overall=%.1f",
        quality.completeness, quality.clarity, quality.consistency, quality.overall,
    )

    # Detect compliance tags
    all_compliance_tags: List[dict] = []
    for section in sections:
        heading = section.get("heading", "Untitled")
        content = section.get("content", "")
        section_index = section.get("section_index", 0)

        try:
            tags = await detect_compliance_tags_in_section(heading, content, section_index)
            for tag in tags:
                all_compliance_tags.append(tag.model_dump())
        except Exception as exc:
            error_msg = f"Compliance detection failed for section {section_index}: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)

    logger.info(
        "Quality node complete: score=%.1f, %d compliance tags",
        quality.overall, len(all_compliance_tags),
    )

    return {
        **state,
        "quality_score": quality.model_dump(),
        "compliance_tags": all_compliance_tags,
        "errors": errors,
    }
