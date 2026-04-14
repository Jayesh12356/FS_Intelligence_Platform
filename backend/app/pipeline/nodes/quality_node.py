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

COMPLIANCE_SYSTEM_PROMPT = """You are a compliance officer reviewing Functional Specifications for regulatory and security risk. You tag sections that require special implementation attention due to legal, financial, or data-protection obligations.

TASK: Identify which compliance domains this section touches. Apply tags ONLY when the section contains concrete functionality in that domain — not when it merely mentions a term in passing.

TAG DEFINITIONS (apply only when the section describes actionable requirements):

1. "payments" — Processes, transmits, or stores monetary transactions: charges, refunds, invoicing, billing cycles, payment method storage, financial reconciliation. Triggers PCI-DSS considerations.
2. "auth" — Implements authentication (login, MFA, SSO, token issuance) or authorization (role checks, permission gates, session management, access control lists). Triggers identity security review.
3. "pii" — Collects, stores, processes, or transmits Personally Identifiable Information: names, emails, phone numbers, addresses, national IDs, health records, biometric data, location data. Triggers GDPR/CCPA/HIPAA considerations.
4. "external_api" — Integrates with third-party services: REST/SOAP calls, webhooks, OAuth flows with external providers, data exchange with partner systems. Triggers vendor dependency and SLA review.
5. "security" — Implements cryptographic operations (encryption at rest/transit, hashing, key management), vulnerability handling, input sanitization, CORS/CSP policies, firewall rules, or intrusion detection.
6. "data_retention" — Defines how long data is kept, when it is deleted, archival procedures, backup/restore policies, right-to-erasure flows, or audit log retention periods.

PRECISION RULES:
- Tag only when the section describes FUNCTIONAL requirements in that domain, not when it references the domain abstractly
- A section can have MULTIPLE tags if it crosses domains (e.g., a user registration form is both "auth" and "pii")
- "reason" must cite the SPECIFIC text or functionality that triggers the tag

Return a JSON array. Empty [] if the section has no compliance-relevant functionality.

Example:
[
  {
    "tag": "pii",
    "reason": "Section requires collecting user's full name, email, and phone number during registration and storing them in the user profile database."
  },
  {
    "tag": "auth",
    "reason": "Section specifies JWT-based session management with refresh tokens and role-based access control for admin vs. regular users."
  }
]

Return ONLY a valid JSON array. No markdown fences, no prose outside the array."""

COMPLIANCE_USER_PROMPT = """Determine which compliance domains this section's requirements fall under. Tag only domains where the section describes concrete, implementable functionality — not passing references.

Section: "{heading}"

{content}

Return a JSON array of compliance tags. If no compliance-relevant functionality is described, return []."""

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

    valid_range = set(range(total_sections))

    # Clarity: % of sections without ambiguities
    sections_with_ambiguities = set()
    for amb in ambiguities:
        idx = amb.get("section_index", -1)
        if idx in valid_range:
            sections_with_ambiguities.add(idx)
    clarity = ((total_sections - len(sections_with_ambiguities)) / total_sections) * 100.0

    # Completeness: % of sections without edge case gaps
    sections_with_gaps = set()
    for gap in edge_cases:
        idx = gap.get("section_index", -1)
        if idx in valid_range:
            sections_with_gaps.add(idx)
    completeness = ((total_sections - len(sections_with_gaps)) / total_sections) * 100.0

    # Consistency: based on contradiction rate
    max_pairs = total_sections * (total_sections - 1) / 2 if total_sections > 1 else 1
    contradiction_rate = len(contradictions) / max_pairs if max_pairs > 0 else 0
    consistency = (1.0 - contradiction_rate) * 100.0

    # Clamp all sub-scores to [0, 100]
    completeness = max(0.0, min(100.0, completeness))
    clarity = max(0.0, min(100.0, clarity))
    consistency = max(0.0, min(100.0, consistency))

    # Overall weighted average
    overall = (
        WEIGHT_COMPLETENESS * completeness
        + WEIGHT_CLARITY * clarity
        + WEIGHT_CONSISTENCY * consistency
    )
    overall = max(0.0, min(100.0, overall))

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
