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
from app.pipeline.state import AmbiguityFlag, FSAnalysisState, Severity

logger = logging.getLogger(__name__)

# ── Prompt Templates ────────────────────────────────────

AMBIGUITY_SYSTEM_PROMPT = """You are an expert requirements analyst specializing in Functional Specification (FS) documents for enterprise software systems.

Your task is to identify AMBIGUOUS, VAGUE, or INCOMPLETE requirements in a given section of an FS document. Focus on:

1. **Vague language**: Words like "should", "may", "appropriate", "etc.", "and/or", "as needed", "relevant", "similar", "reasonable" without clear criteria
2. **Missing quantification**: Requirements without measurable thresholds (e.g., "fast response" without specifying milliseconds)
3. **Undefined references**: References to undefined terms, roles, or systems
4. **Incomplete logic**: Missing error handling, edge cases, or boundary conditions
5. **Conflicting statements**: Requirements that could be interpreted in multiple ways

For each ambiguity found, provide:
- The exact flagged text (quote from the section)
- A clear reason why it's ambiguous
- Severity: HIGH (blocks development), MEDIUM (causes confusion), LOW (minor clarification needed)
- A specific clarification question for the functional team

Return your analysis as a JSON array. If no ambiguities found, return an empty array [].

Example output format:
```json
[
  {
    "flagged_text": "The system should respond quickly",
    "reason": "No measurable performance threshold defined. 'Quickly' is subjective.",
    "severity": "HIGH",
    "clarification_question": "What is the maximum acceptable response time in milliseconds for 95th percentile?"
  },
  {
    "flagged_text": "and other relevant data",
    "reason": "'Other relevant data' is undefined. Developers cannot determine what data to include.",
    "severity": "MEDIUM",
    "clarification_question": "Please list all specific data fields that should be included."
  }
]
```

IMPORTANT: Return ONLY a valid JSON array. No markdown, no explanations outside the JSON."""

AMBIGUITY_USER_PROMPT = """Analyze the following FS document section for ambiguities:

## Section: {heading}

{content}

---
Return a JSON array of ambiguity flags. If no ambiguities are found, return [].
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

    client = get_llm_client()
    prompt = AMBIGUITY_USER_PROMPT.format(heading=heading, content=content)

    try:
        result = await client.call_llm_json(
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
