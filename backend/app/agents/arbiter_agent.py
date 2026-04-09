"""ArbiterAgent — reads both arguments and makes the final verdict.

Part of the adversarial validation system (L6).
This agent impartially evaluates the RedAgent's and BlueAgent's arguments
and renders a final verdict: AMBIGUOUS or CLEAR.
"""

import logging

from crewai import Agent

from app.agents.llm_config import get_crewai_llm

logger = logging.getLogger(__name__)

ARBITER_AGENT_ROLE = "Impartial Requirements Arbiter"

ARBITER_AGENT_GOAL = (
    "Evaluate both arguments fairly and render a final verdict on whether "
    "the requirement is AMBIGUOUS or CLEAR. Your verdict must be well-reasoned, "
    "and you must assign a confidence score (0-100) to your decision."
)

ARBITER_AGENT_BACKSTORY = (
    "You are a principal architect with 20 years of experience bridging the "
    "gap between functional teams and development teams. You have mediated "
    "thousands of specification disputes. You weigh evidence objectively: "
    "if the ambiguity would genuinely block implementation or lead to "
    "incorrect builds, you rule AMBIGUOUS. If the concern is theoretical "
    "or easily resolved by standard engineering practice, you rule CLEAR. "
    "You are known for precise, well-calibrated judgements."
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
