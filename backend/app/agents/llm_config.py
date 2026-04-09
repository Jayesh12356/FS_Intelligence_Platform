"""CrewAI LLM configuration — maps project settings to CrewAI's LLM class.

This ensures CrewAI agents use the same LLM provider and model
configured in the project's .env / settings.
"""

import logging

from crewai import LLM

from app.config import get_settings

logger = logging.getLogger(__name__)


def get_crewai_llm() -> LLM:
    """Create a CrewAI LLM instance using the project's LLM settings.

    Maps the project's LLM_PROVIDER and PRIMARY_MODEL to CrewAI's
    provider format (e.g., 'anthropic/claude-sonnet-4-20250514').

    Returns:
        CrewAI LLM configured with the project's API keys and model.
    """
    settings = get_settings()

    if settings.LLM_PROVIDER == "openai":
        model_str = f"openai/{settings.PRIMARY_MODEL}"
        api_key = settings.OPENAI_API_KEY
    else:
        model_str = f"anthropic/{settings.PRIMARY_MODEL}"
        api_key = settings.ANTHROPIC_API_KEY

    logger.debug("CrewAI LLM configured: %s", model_str)

    return LLM(
        model=model_str,
        api_key=api_key,
        temperature=0.0,
    )
