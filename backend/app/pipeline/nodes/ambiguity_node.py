"""Ambiguity detection node — uses LLM to flag vague/incomplete requirements.

This is the core L3 feature. For each parsed section, the node:
1. Sends the section text to the LLM with a structured prompt
2. Parses the JSON response into AmbiguityFlag objects
3. Accumulates all flags into the pipeline state

The node uses the unified LLM client (no direct SDK imports).
"""

import logging
from typing import List

from app.llm import get_llm_client
from app.orchestration.pipeline_llm import pipeline_call_llm_json
from app.pipeline.state import AmbiguityFlag, FSAnalysisState, Severity

logger = logging.getLogger(__name__)

# ── Prompt Templates ────────────────────────────────────

AMBIGUITY_SYSTEM_PROMPT = """You are a principal requirements analyst with 20 years of experience auditing Functional Specifications for enterprise software. Your analysis directly determines whether a developer can implement a requirement correctly on the first attempt.

TASK: Identify requirements that a developer CANNOT implement without making assumptions. Flag only genuine ambiguities — not stylistic preferences, not theoretical concerns, not intentional flexibility.

DETECTION CATEGORIES (check each systematically):

1. UNQUANTIFIED THRESHOLDS — "fast", "quickly", "large", "significant", "reasonable", "timely" with no numeric bound. A developer cannot write a performance test without a number.
2. UNDEFINED REFERENCES — terms, roles, systems, or data fields mentioned but never defined anywhere in the section. If "the admin" is referenced but admin role is not specified, flag it.
3. MISSING BEHAVIOR — "the system handles errors" without specifying HOW (retry? log? notify? fail silently?). A developer will guess and guess wrong.
4. AMBIGUOUS SCOPE — "and other relevant data", "etc.", "as needed", "similar functionality". A developer cannot determine the boundary of what to build.
5. CONDITIONAL GAPS — "if applicable", "when appropriate", "under certain conditions" without defining the conditions.
6. CONTRADICTORY WITHIN SECTION — two sentences in the same section that cannot both be true.

SEVERITY CALIBRATION:
- HIGH: Two competent developers would build DIFFERENT things from this text. Blocks implementation. Requires clarification before coding begins.
- MEDIUM: The intent is mostly clear but a developer must make a non-trivial assumption. Could lead to rework if the assumption is wrong.
- LOW: Minor imprecision that an experienced developer can reasonably infer from context. Low risk of incorrect implementation.

DO NOT FLAG:
- Intentional flexibility (e.g., "the admin can configure the threshold" — this is a feature, not ambiguity)
- Standard industry terms used correctly (e.g., "REST API", "OAuth2", "CRUD")
- Requirements that are clear in context even if imprecise in isolation

OUTPUT RULES:
- "flagged_text" must be an EXACT quote from the section — copy-paste, not paraphrased
- "reason" must explain specifically what a developer cannot determine
- "clarification_question" must be answerable with a concrete, measurable response

Return a JSON array. Empty array [] if no genuine ambiguities exist.

Example:
[
  {
    "flagged_text": "The system should respond quickly to user requests",
    "reason": "No response time threshold defined. A developer cannot write a performance test or set an SLA without a specific number.",
    "severity": "HIGH",
    "clarification_question": "What is the maximum acceptable response time in milliseconds at the 95th percentile under normal load?"
  }
]

Return ONLY a valid JSON array. No markdown fences, no prose outside the array."""

AMBIGUITY_USER_PROMPT = """Audit the following FS section. For every sentence containing a requirement (shall/must/should/will), determine whether a developer can implement it WITHOUT guessing. Flag only genuine ambiguities.

Section: "{heading}"

{content}

Return a JSON array of ambiguity flags. If every requirement is implementable as written, return [].
"""


# ── Detection Function ──────────────────────────────────


async def detect_ambiguities_in_section(
    heading: str,
    content: str,
    section_index: int,
) -> List[AmbiguityFlag]:
    """Detect ambiguities in a single FS section using the LLM.

    Args:
        heading: Section heading text.
        content: Section body text.
        section_index: Index of the section in the document.

    Returns:
        List of AmbiguityFlag objects found in this section.
    """
    if not content or len(content.strip()) < 20:
        logger.debug("Skipping section %d (%s): too short", section_index, heading)
        return []

    prompt = AMBIGUITY_USER_PROMPT.format(heading=heading, content=content)

    try:
        result = await pipeline_call_llm_json(
            prompt=prompt,
            system=AMBIGUITY_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=2048,
        )

        # Parse the result
        if not isinstance(result, list):
            logger.warning("LLM returned non-list for section %d: %s", section_index, type(result))
            return []

        flags: List[AmbiguityFlag] = []
        for item in result:
            try:
                severity_str = item.get("severity", "MEDIUM").upper()
                severity = Severity(severity_str) if severity_str in Severity.__members__ else Severity.MEDIUM

                flag = AmbiguityFlag(
                    section_index=section_index,
                    section_heading=heading,
                    flagged_text=item.get("flagged_text", ""),
                    reason=item.get("reason", ""),
                    severity=severity,
                    clarification_question=item.get("clarification_question", ""),
                )
                flags.append(flag)
            except Exception as exc:
                logger.warning("Failed to parse ambiguity flag: %s — %s", item, exc)

        logger.info(
            "Section %d (%s): found %d ambiguities",
            section_index, heading, len(flags),
        )
        return flags

    except Exception as exc:
        logger.error("Ambiguity detection failed for section %d: %s", section_index, exc)
        return []


# ── LangGraph Node Function ─────────────────────────────


async def ambiguity_node(state: FSAnalysisState) -> FSAnalysisState:
    """LangGraph node: detect ambiguities across all parsed sections.

    Reads state.parsed_sections, runs ambiguity detection on each,
    and populates state.ambiguities with the results.
    """
    sections = state.get("parsed_sections", [])
    all_ambiguities: List[dict] = []
    errors: List[str] = list(state.get("errors", []))

    logger.info("Ambiguity node: analyzing %d sections for fs_id=%s", len(sections), state.get("fs_id", "?"))

    for section in sections:
        heading = section.get("heading", "Untitled")
        content = section.get("content", "")
        section_index = section.get("section_index", 0)

        try:
            flags = await detect_ambiguities_in_section(heading, content, section_index)
            for flag in flags:
                all_ambiguities.append(flag.model_dump())
        except Exception as exc:
            error_msg = f"Ambiguity detection failed for section {section_index}: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)

    logger.info(
        "Ambiguity node complete: %d flags across %d sections",
        len(all_ambiguities), len(sections),
    )

    return {
        **state,
        "ambiguities": all_ambiguities,
        "errors": errors,
    }
