"""DebateCrew — orchestrates the Red vs Blue adversarial debate.

Manages the sequential CrewAI debate:
  1. RedAgent argues the requirement IS ambiguous
  2. BlueAgent argues the requirement IS clear
  3. ArbiterAgent evaluates both and renders a verdict

Usage:
    from app.agents.debate_crew import run_debate
    verdict = await run_debate("The system should respond quickly")
"""

import json
import logging
from typing import Optional

from crewai import Crew, Process, Task

from app.agents.red_agent import create_red_agent
from app.agents.blue_agent import create_blue_agent
from app.agents.arbiter_agent import create_arbiter_agent
from app.pipeline.state import DebateVerdict

logger = logging.getLogger(__name__)


# ── Task Descriptions ──────────────────────────────────


RED_TASK_DESCRIPTION = """Analyze the following requirement that has been flagged as potentially ambiguous.

**Requirement text:**
{requirement_text}

**Why it was flagged:**
{flag_reason}

**Section:** {section_heading}

Your job: Argue convincingly that this requirement IS ambiguous and cannot be
implemented as-is. Identify specific gaps, undefined terms, missing edge cases,
vague language, and contradictory implications. Be thorough and precise.

Provide your argument as a structured analysis with specific points."""

RED_TASK_EXPECTED_OUTPUT = (
    "A detailed argument (3-5 specific points) explaining why this requirement "
    "is ambiguous, with concrete examples of how different developers might "
    "interpret it differently."
)


BLUE_TASK_DESCRIPTION = """You have seen a requirement that was flagged as potentially ambiguous,
and the QA engineer has argued it IS ambiguous.

**Requirement text:**
{requirement_text}

**Section:** {section_heading}

**QA Engineer's argument (RedAgent):**
The QA engineer has already presented their case for why this is ambiguous.

Your job: Defend this requirement as CLEAR and implementable. Explain how a
competent developer would interpret and build from this requirement using
standard engineering practices and domain knowledge. Counter the QA engineer's
concerns point by point.

Provide your defense as a structured rebuttal with specific points."""

BLUE_TASK_EXPECTED_OUTPUT = (
    "A detailed defense (3-5 specific points) explaining why this requirement "
    "is clear enough to implement, with references to standard practices and "
    "reasonable assumptions."
)


ARBITER_TASK_DESCRIPTION = """You must evaluate the debate between the QA Engineer and the Senior Developer
about whether a requirement is ambiguous or clear.

**Requirement text:**
{requirement_text}

**Section:** {section_heading}

Both sides have presented their arguments. Review them carefully and render
your final verdict.

You MUST respond with ONLY a valid JSON object in this exact format:
{{
  "verdict": "AMBIGUOUS" or "CLEAR",
  "reasoning": "Your detailed reasoning for the verdict (2-3 sentences)",
  "confidence": <integer 0-100>
}}

Rules for your verdict:
- If the ambiguity would genuinely block implementation or lead to incorrect
  builds, rule AMBIGUOUS
- If the concern is theoretical or easily resolved by standard engineering
  practice, rule CLEAR
- Confidence should reflect how certain you are (>80 = strong, 50-80 = moderate, <50 = weak)

IMPORTANT: Return ONLY the JSON object. No markdown, no extra text."""

ARBITER_TASK_EXPECTED_OUTPUT = (
    'A JSON object with keys: "verdict" (AMBIGUOUS or CLEAR), '
    '"reasoning" (string), "confidence" (integer 0-100).'
)


# ── Debate Runner ──────────────────────────────────────


async def run_debate(
    requirement_text: str,
    flag_reason: str = "",
    section_heading: str = "Unknown Section",
) -> DebateVerdict:
    """Run a full adversarial debate on a single requirement.

    Creates a CrewAI crew with Red, Blue, and Arbiter agents,
    runs them sequentially, and parses the arbiter's verdict.

    Args:
        requirement_text: The requirement text to debate.
        flag_reason: Why the ambiguity detector flagged this text.
        section_heading: The section heading for context.

    Returns:
        DebateVerdict with verdict, arguments, reasoning, and confidence.
    """
    logger.info(
        "Starting adversarial debate for section '%s' (text: %.60s…)",
        section_heading,
        requirement_text,
    )

    # Create agents
    red_agent = create_red_agent()
    blue_agent = create_blue_agent()
    arbiter_agent = create_arbiter_agent()

    # Create tasks with context
    format_kwargs = {
        "requirement_text": requirement_text,
        "flag_reason": flag_reason,
        "section_heading": section_heading,
    }

    red_task = Task(
        description=RED_TASK_DESCRIPTION.format(**format_kwargs),
        expected_output=RED_TASK_EXPECTED_OUTPUT,
        agent=red_agent,
    )

    blue_task = Task(
        description=BLUE_TASK_DESCRIPTION.format(**format_kwargs),
        expected_output=BLUE_TASK_EXPECTED_OUTPUT,
        agent=blue_agent,
        context=[red_task],  # Blue sees Red's output
    )

    arbiter_task = Task(
        description=ARBITER_TASK_DESCRIPTION.format(**format_kwargs),
        expected_output=ARBITER_TASK_EXPECTED_OUTPUT,
        agent=arbiter_agent,
        context=[red_task, blue_task],  # Arbiter sees both
    )

    # Create and run the crew
    crew = Crew(
        agents=[red_agent, blue_agent, arbiter_agent],
        tasks=[red_task, blue_task, arbiter_task],
        process=Process.sequential,
        verbose=False,
    )

    try:
        result = crew.kickoff()

        # Extract individual task outputs
        red_argument = _extract_task_output(result, 0, "Red argument unavailable")
        blue_argument = _extract_task_output(result, 1, "Blue argument unavailable")
        arbiter_raw = _extract_task_output(result, 2, "")

        # Parse arbiter's JSON verdict
        verdict_data = _parse_arbiter_verdict(arbiter_raw)

        debate_verdict = DebateVerdict(
            verdict=verdict_data.get("verdict", "AMBIGUOUS"),
            red_argument=red_argument,
            blue_argument=blue_argument,
            arbiter_reasoning=verdict_data.get("reasoning", arbiter_raw),
            confidence=verdict_data.get("confidence", 50),
        )

        logger.info(
            "Debate complete: verdict=%s, confidence=%d, section='%s'",
            debate_verdict.verdict,
            debate_verdict.confidence,
            section_heading,
        )

        return debate_verdict

    except Exception as exc:
        logger.error("Debate crew failed: %s", exc)
        # Return a safe fallback — keep the ambiguity flag
        return DebateVerdict(
            verdict="AMBIGUOUS",
            red_argument=f"Debate failed: {exc}",
            blue_argument="Debate failed — defaulting to AMBIGUOUS for safety",
            arbiter_reasoning=f"Debate execution error: {exc}. Defaulting to AMBIGUOUS.",
            confidence=0,
        )


def _extract_task_output(result: object, task_index: int, fallback: str) -> str:
    """Extract the output text from a CrewAI task result.

    Args:
        result: The CrewAI crew kickoff result.
        task_index: Index of the task in the crew's task list.
        fallback: Default text if extraction fails.

    Returns:
        The task's output text.
    """
    try:
        # CrewAI stores task outputs in result.tasks_output
        if hasattr(result, "tasks_output") and len(result.tasks_output) > task_index:
            task_output = result.tasks_output[task_index]
            if hasattr(task_output, "raw"):
                return str(task_output.raw)
            return str(task_output)
        # Fallback: try the raw result
        if task_index == 2 and hasattr(result, "raw"):
            return str(result.raw)
        return fallback
    except Exception as exc:
        logger.warning("Failed to extract task %d output: %s", task_index, exc)
        return fallback


def _parse_arbiter_verdict(raw_text: str) -> dict:
    """Parse the arbiter's JSON verdict from raw output text.

    Handles common LLM quirks like markdown code blocks.

    Args:
        raw_text: Raw text output from the arbiter agent.

    Returns:
        Parsed dictionary with verdict, reasoning, confidence.
    """
    cleaned = raw_text.strip()

    # Strip markdown code block wrappers
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        # Validate and normalise
        verdict = data.get("verdict", "AMBIGUOUS").upper()
        if verdict not in ("AMBIGUOUS", "CLEAR"):
            verdict = "AMBIGUOUS"
        data["verdict"] = verdict

        confidence = data.get("confidence", 50)
        if not isinstance(confidence, (int, float)):
            confidence = 50
        data["confidence"] = max(0, min(100, int(confidence)))

        return data

    except (json.JSONDecodeError, AttributeError) as exc:
        logger.warning("Failed to parse arbiter verdict JSON: %s — raw: %.200s", exc, raw_text)
        # Try to extract verdict from text
        upper_text = raw_text.upper()
        if "CLEAR" in upper_text and "AMBIGUOUS" not in upper_text:
            return {"verdict": "CLEAR", "reasoning": raw_text, "confidence": 40}
        return {"verdict": "AMBIGUOUS", "reasoning": raw_text, "confidence": 30}
