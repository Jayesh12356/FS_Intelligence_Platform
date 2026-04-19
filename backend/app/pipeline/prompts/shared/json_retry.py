"""Strict-JSON retry suffix.

Appended to the user prompt on the second attempt when the first response
was unparseable. Kept intentionally short: the model has already seen the
full contract once and needs a compact reminder, not a second copy.
"""

NAME = "shared.json_retry"

RETRY_SUFFIX = (
    "\n\nSTRICT RETRY: your previous response could not be parsed as JSON.\n"
    "Return ONLY a valid JSON value matching the contract.\n"
    "No Markdown fences, no commentary, no trailing text."
)


def build(first_user_prompt: str) -> str:
    """Return the retry prompt to send on attempt 2."""
    return first_user_prompt.rstrip() + RETRY_SUFFIX


__all__ = ["NAME", "RETRY_SUFFIX", "build"]
