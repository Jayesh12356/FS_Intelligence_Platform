"""RedAgent — argues the requirement IS ambiguous.

Part of the adversarial validation system (L6).
This agent takes a skeptical QA stance and finds every possible
edge case and ambiguity in a given requirement.
"""

import logging

from crewai import Agent

from app.agents.llm_config import get_crewai_llm

logger = logging.getLogger(__name__)

RED_AGENT_ROLE = "Skeptical QA Engineer"

RED_AGENT_GOAL = (
    "Find all reasons this requirement is unclear, incomplete, or ambiguous. "
    "Argue convincingly that the requirement cannot be implemented as-is "
    "without further clarification from the functional team."
)

RED_AGENT_BACKSTORY = (
    "You are a skeptical QA engineer who has spent 15 years finding every "
    "edge case and ambiguity in requirements documents. You have seen "
    "countless projects fail because of vague specifications. You know that "
    "'obvious' interpretations are often wrong, and you challenge every "
    "assumption. You believe it is ALWAYS better to flag an ambiguity than "
    "to let it through, because the cost of rework far exceeds the cost of "
    "a clarification question."
)


def create_red_agent() -> Agent:
    """Create the RedAgent that argues a requirement IS ambiguous.

    Returns:
        CrewAI Agent configured as a skeptical QA engineer.
    """
    llm = get_crewai_llm()

    agent = Agent(
        role=RED_AGENT_ROLE,
        goal=RED_AGENT_GOAL,
        backstory=RED_AGENT_BACKSTORY,
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    logger.debug("Created RedAgent (skeptical QA)")
    return agent
