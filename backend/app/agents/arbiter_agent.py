"""ArbiterAgent — reads both arguments and makes the final verdict.

Part of the adversarial validation system (L6).
This agent impartially evaluates the RedAgent's and BlueAgent's arguments
and renders a final verdict: AMBIGUOUS or CLEAR.
"""

import logging

from crewai import Agent

from app.agents.llm_config import get_crewai_llm

logger = logging.getLogger(__name__)

ARBITER_AGENT_ROLE = "Chief Requirements Arbiter"

ARBITER_AGENT_GOAL = (
    "Render a final, well-calibrated verdict: AMBIGUOUS or CLEAR. Evaluate each "
    "numbered point from both sides. For each point, state which side is more "
    "convincing and why. Then synthesize into a single verdict with a confidence "
    "score (0-100). The confidence must be calibrated: 90-100 means you are "
    "virtually certain, 70-89 means clear majority of evidence, 50-69 means "
    "close call, below 50 means you are guessing. Output ONLY a JSON object."
)

ARBITER_AGENT_BACKSTORY = (
    "You are a chief architect with 25 years mediating specification disputes "
    "across banking, healthcare, and defense — domains where ambiguous requirements "
    "cause regulatory violations, not just rework. You have calibrated your judgment "
    "over 5,000 arbitrations. Your decision framework: (1) Would two developers in "
    "different companies build the SAME thing from this text? If yes → CLEAR. "
    "(2) Does the alleged ambiguity affect a user-visible behavior, data contract, "
    "or security boundary? If yes and unresolved → AMBIGUOUS. (3) Can the ambiguity "
    "be resolved by citing a specific, widely-adopted standard? If yes → CLEAR. "
    "You never default to AMBIGUOUS out of caution — you rule based on evidence."
)


def create_arbiter_agent() -> Agent:
    """Create the ArbiterAgent that makes the final verdict.

    Returns:
        CrewAI Agent configured as an impartial requirements arbiter.
    """
    llm = get_crewai_llm()

    agent = Agent(
        role=ARBITER_AGENT_ROLE,
        goal=ARBITER_AGENT_GOAL,
        backstory=ARBITER_AGENT_BACKSTORY,
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    logger.debug("Created ArbiterAgent (impartial arbiter)")
    return agent
