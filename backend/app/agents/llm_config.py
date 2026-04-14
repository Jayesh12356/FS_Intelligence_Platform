"""CrewAI LLM configuration — maps project settings to CrewAI's LLM class.

This ensures CrewAI agents use the same LLM provider and model
configured in the project's .env / settings.
"""

import logging

from crewai import LLM

from app.config import get_settings

logger = logging.getLogger(__name__)

_PROVIDER_KEY_MAP = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def get_crewai_llm() -> LLM:
    """Create a CrewAI LLM instance using the project's LLM settings.

    Maps the project's LLM_PROVIDER and PRIMARY_MODEL to LiteLLM's
    provider prefix format (e.g., 'openrouter/deepseek/deepseek-v3.2').

    When provider is openrouter and REASONING_MODEL is set, uses that
    model for debate agents (the hardest reasoning task).

    Returns:
        CrewAI LLM configured with the project's API keys and model.
    """
    settings = get_settings()
    provider = settings.LLM_PROVIDER.lower().strip()

    key_attr = _PROVIDER_KEY_MAP.get(provider, "ANTHROPIC_API_KEY")
    api_key = getattr(settings, key_attr, "")

    base_model = settings.PRIMARY_MODEL
    if provider == "openrouter" and settings.REASONING_MODEL.strip():
        base_model = settings.REASONING_MODEL.strip()

    model_str = f"{provider}/{base_model}"

    logger.debug("CrewAI LLM configured: provider=%s, model=%s", provider, model_str)

    return LLM(
        model=model_str,
        api_key=api_key,
        temperature=0.0,
    )
