"""Debate node — adversarial validation of HIGH severity ambiguity flags.

LangGraph pipeline node (L6) that wraps the CrewAI debate crew.
For each HIGH severity ambiguity flag, runs a Red vs Blue debate.
If the arbiter rules CLEAR, the flag is removed from state.ambiguities.
If the arbiter rules AMBIGUOUS, the flag is kept with debate reasoning added.
"""

import logging
from typing import List

from app.agents.debate_crew import run_debate
from app.pipeline.state import DebateVerdict, FSAnalysisState

logger = logging.getLogger(__name__)


async def debate_node(state: FSAnalysisState) -> FSAnalysisState:
    """LangGraph node: run adversarial debate on HIGH severity ambiguity flags.

    For each ambiguity with severity == HIGH:
      1. Run the CrewAI debate (RedAgent vs BlueAgent → ArbiterAgent)
      2. If verdict == CLEAR: remove the flag from ambiguities
      3. If verdict == AMBIGUOUS: keep the flag, attach debate reasoning

    Also records debate results for benchmark tracking and UI display.

    Args:
        state: Current pipeline state with ambiguities populated.

    Returns:
        Updated state with filtered ambiguities and debate_results.
    """
    ambiguities = list(state.get("ambiguities", []))
    errors = list(state.get("errors", []))
    fs_id = state.get("fs_id", "?")

    # Separate HIGH severity flags for debate
    high_flags = [a for a in ambiguities if a.get("severity") == "HIGH"]
    other_flags = [a for a in ambiguities if a.get("severity") != "HIGH"]

    logger.info(
        "Debate node: %d HIGH severity flags to debate (of %d total) for fs_id=%s",
        len(high_flags),
        len(ambiguities),
        fs_id,
    )

    if not high_flags:
        logger.info("Debate node: no HIGH severity flags — skipping debate")
        return {
            **state,
            "debate_results": [],
            "errors": errors,
        }

    # Run debates and collect results
    debate_results: List[dict] = []
    surviving_high_flags: List[dict] = []
    cleared_count = 0

    for flag in high_flags:
        flagged_text = flag.get("flagged_text", "")
        flag_reason = flag.get("reason", "")
        section_heading = flag.get("section_heading", "Unknown")
        section_index = flag.get("section_index", 0)

        try:
            verdict: DebateVerdict = await run_debate(
                requirement_text=flagged_text,
                flag_reason=flag_reason,
                section_heading=section_heading,
            )

            # Build debate result record
            debate_result = {
                "section_index": section_index,
                "section_heading": section_heading,
                "flagged_text": flagged_text,
                "original_reason": flag_reason,
                "verdict": verdict.verdict,
                "red_argument": verdict.red_argument,
                "blue_argument": verdict.blue_argument,
                "arbiter_reasoning": verdict.arbiter_reasoning,
                "confidence": verdict.confidence,
            }
            debate_results.append(debate_result)

            if verdict.verdict == "CLEAR":
                # Flag overridden by debate — remove from ambiguities
                cleared_count += 1
                logger.info(
                    "Debate CLEARED flag in section %d (%s) — confidence=%d",
                    section_index,
                    section_heading,
                    verdict.confidence,
                )
            else:
                # Flag confirmed — keep it, add debate reasoning
                enriched_flag = {
                    **flag,
                    "debate_reasoning": verdict.arbiter_reasoning,
                    "debate_confidence": verdict.confidence,
                }
                surviving_high_flags.append(enriched_flag)
                logger.info(
                    "Debate CONFIRMED flag in section %d (%s) — confidence=%d",
                    section_index,
                    section_heading,
                    verdict.confidence,
                )

        except Exception as exc:
            error_msg = f"Debate failed for section {section_index}: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)
            # On error, keep the flag (fail-safe)
            surviving_high_flags.append(flag)

    # Merge surviving HIGH flags with other flags
    final_ambiguities = other_flags + surviving_high_flags

    # Log win rate for benchmark tracking
    total_debated = len(high_flags)
    red_wins = total_debated - cleared_count  # AMBIGUOUS verdicts
    blue_wins = cleared_count  # CLEAR verdicts
    red_win_rate = (red_wins / total_debated * 100) if total_debated > 0 else 0

    logger.info(
        "Debate node complete for fs_id=%s: "
        "%d debated, %d confirmed (RED wins), %d cleared (BLUE wins), "
        "red_win_rate=%.1f%%, %d final ambiguities",
        fs_id,
        total_debated,
        red_wins,
        blue_wins,
        red_win_rate,
        len(final_ambiguities),
    )

    return {
        **state,
        "ambiguities": final_ambiguities,
        "debate_results": debate_results,
        "errors": errors,
    }
