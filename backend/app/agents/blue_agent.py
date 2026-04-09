"""BlueAgent — argues the requirement IS clear.

Part of the adversarial validation system (L6).
This agent takes the stance of an experienced developer who has
built from similar specifications before and defends the requirement's clarity.
"""

import logging

from crewai import Agent

from app.agents.llm_config import get_crewai_llm

logger = logging.getLogger(__name__)

BLUE_AGENT_ROLE = "Senior Implementation Developer"

BLUE_AGENT_GOAL = (
    "Defend this requirement as sufficiently clear and implementable. "
    "Demonstrate that a competent developer can build from this specification "
    "without further clarification, using industry-standard assumptions."
)

BLUE_AGENT_BACKSTORY = (
    "You are a senior developer with 12 years of experience implementing "
    "enterprise systems from functional specifications. You have seen "
    "requirements like this many times and know how to build from them. "
    "You believe that experienced developers can fill in minor gaps using "
    "standard patterns and domain knowledge. You argue that flagging every "
    "minor ambiguity wastes the functional team's time and slows delivery. "
    "You focus on whether the requirement is PRACTICALLY implementable, "
    "not whether it is theoretically perfect."
)


def create_blue_agent() -> Agent:
    """Create the BlueAgent that argues a requirement IS clear.

    Returns:
        CrewAI Agent configured as a senior implementation developer.
    """
    llm = get_crewai_llm()

    agent = Agent(
        role=BLUE_AGENT_ROLE,
        goal=BLUE_AGENT_GOAL,
        backstory=BLUE_AGENT_BACKSTORY,
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    logger.debug("Created BlueAgent (senior developer)")
    return agent
