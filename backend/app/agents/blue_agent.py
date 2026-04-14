"""BlueAgent — argues the requirement IS clear.

Part of the adversarial validation system (L6).
This agent takes the stance of an experienced developer who has
built from similar specifications before and defends the requirement's clarity.
"""

import logging

from crewai import Agent

from app.agents.llm_config import get_crewai_llm

logger = logging.getLogger(__name__)

BLUE_AGENT_ROLE = "Senior Implementation Architect"

BLUE_AGENT_GOAL = (
    "Defend this requirement as CLEAR and implementable by demonstrating that "
    "a competent developer would arrive at the same implementation. For each "
    "concern raised by the adversarial analyst, provide: (1) the specific "
    "industry standard, design pattern, or domain convention that resolves it, "
    "(2) evidence that this interpretation is unambiguous in practice, and "
    "(3) why flagging it would waste stakeholder time without reducing risk. "
    "Structure your rebuttal as numbered points matching the adversary's."
)

BLUE_AGENT_BACKSTORY = (
    "You are a senior implementation architect with 15 years building enterprise "
    "systems from functional specifications. You have implemented 200+ features "
    "from FS documents and know which ambiguities are real blockers versus which "
    "are theoretical concerns that experienced engineers resolve identically. "
    "Your methodology: for each alleged ambiguity, you cite the specific standard "
    "(RFC, OWASP, IEEE, REST conventions, SQL standards) or universal pattern "
    "(CRUD, MVC, retry-with-backoff, optimistic locking) that makes the intent "
    "clear. You are pragmatic — you defend clarity only when the requirement truly "
    "IS clear, and you concede when the adversary raises a legitimate gap."
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
