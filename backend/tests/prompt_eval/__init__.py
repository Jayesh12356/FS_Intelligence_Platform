"""Prompt-evaluation harness.

This sub-package validates every v2 prompt (``app.pipeline.prompts.*``)
against structural guarantees and — when ``PROMPT_EVAL_LIVE=1`` is set —
against a live LLM.

Modes:

``CI`` (default)
    Runs entirely offline. A stub LLM returns a canned response per
    prompt. The harness asserts that:
      * the system prompt contains the required sections (ROLE, MISSION,
        CONSTRAINTS, OUTPUT CONTRACT);
      * the declared output schema is self-consistent;
      * example fixtures render deterministically (no KeyError, no
        trailing whitespace drift).

``live`` (``PROMPT_EVAL_LIVE=1``)
    Calls the real LLM exactly once per fixture and checks that the
    returned JSON/text matches the declared OutputContract. Use
    sparingly — costs real tokens.

``diff`` (``PROMPT_EVAL_DIFF=1``)
    Compares the v2 prompt against a recorded golden baseline stored in
    ``backend/tests/prompt_eval/golden/``. Fails if any structural field
    (role, mission, constraint count, schema keys) drifted without a
    corresponding golden update. Use this as the regression gate in CI.
"""
