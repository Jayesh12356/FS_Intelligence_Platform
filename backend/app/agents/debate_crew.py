"""DebateCrew — orchestrates the Red vs Blue adversarial debate.

Manages the sequential CrewAI debate:
  1. RedAgent argues the requirement IS ambiguous
  2. BlueAgent argues the requirement IS clear
  3. ArbiterAgent evaluates both and renders a verdict

Usage:
    from app.agents.debate_crew import run_debate
    verdict = await run_debate("The system should respond quickly")
"""

import asyncio
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


RED_TASK_DESCRIPTION = """A requirement has been flagged for adversarial review.

REQUIREMENT: "{requirement_text}"
FLAG REASON: {flag_reason}
SECTION: {section_heading}

Your task: Prove this requirement is AMBIGUOUS by constructing 3-5 numbered points. For EACH point:
1. Quote the exact ambiguous phrase from the requirement
2. Provide TWO plausible but mutually exclusive developer interpretations
3. Explain the business consequence if the wrong interpretation is chosen

Focus on ambiguities that affect: data contracts, user-visible behavior, security boundaries, error handling, and performance expectations. Do NOT flag stylistic issues or theoretical edge cases with negligible impact."""

RED_TASK_EXPECTED_OUTPUT = (
    "3-5 numbered points, each containing: the ambiguous phrase (quoted), "
    "two concrete conflicting interpretations, and the business impact of "
    "choosing the wrong one."
)


BLUE_TASK_DESCRIPTION = """The adversarial analyst has argued this requirement is ambiguous. You must rebut their argument.

REQUIREMENT: "{requirement_text}"
SECTION: {section_heading}

The adversarial analyst has presented numbered points arguing ambiguity. For EACH of their points, provide a numbered rebuttal:
1. Cite the specific standard, pattern, or convention that resolves the alleged ambiguity (e.g., RFC 7231, OWASP ASVS, REST conventions, SQL ACID guarantees, IEEE 830)
2. Explain why any competent developer in this domain would arrive at the same implementation
3. If the point has SOME merit, concede it explicitly rather than making a weak defense

Only defend points that are genuinely clear. If a point is legitimately ambiguous, say so — your credibility depends on honest assessment, not blind defense."""

BLUE_TASK_EXPECTED_OUTPUT = (
    "Numbered rebuttals matching the adversary's points. Each contains: "
    "the standard/convention that resolves it, why the interpretation is "
    "unambiguous in practice, or an honest concession if the point is valid."
)


ARBITER_TASK_DESCRIPTION = """Evaluate the debate and render a final verdict.

REQUIREMENT: "{requirement_text}"
SECTION: {section_heading}

Both sides have presented numbered arguments. For each contested point, determine which side is more convincing, then synthesize a final verdict.

DECISION FRAMEWORK:
1. For each point: would two developers at different companies build the SAME thing? If no → point favors AMBIGUOUS.
2. Does the alleged ambiguity affect user-visible behavior, data contracts, or security? If yes and unresolved → favors AMBIGUOUS.
3. Did the defender cite a specific, widely-adopted standard that resolves it? If yes → point favors CLEAR.
4. Did the defender concede the point? If yes → point favors AMBIGUOUS.

CONFIDENCE CALIBRATION:
  90-100: All/nearly all points favor one side overwhelmingly
  70-89: Clear majority of evidence favors one side
  50-69: Close call, roughly balanced arguments
  Below 50: Evidence is ambiguous (default to AMBIGUOUS verdict in this case)

You MUST respond with ONLY a valid JSON object:
{{
  "verdict": "AMBIGUOUS" or "CLEAR",
  "reasoning": "2-3 sentences summarizing which points were decisive and why",
  "confidence": <integer 0-100>
}}

IMPORTANT: Return ONLY the JSON object. No markdown fences, no extra text."""

ARBITER_TASK_EXPECTED_OUTPUT = (
    'A JSON object with exactly three keys: "verdict" (AMBIGUOUS or CLEAR), '
    '"reasoning" (2-3 sentence summary of decisive points), '
    '"confidence" (integer 0-100, calibrated per the framework above).'
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
        result = await asyncio.to_thread(crew.kickoff)

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
