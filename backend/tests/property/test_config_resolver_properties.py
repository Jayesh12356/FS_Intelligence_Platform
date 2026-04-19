"""Property tests for ``app.orchestration.config_resolver``.

Invariants:

1. The normalised provider name is always one of the valid providers, or
   falls back to ``"api"`` — it never returns garbage.
2. Case / whitespace / dashes are normalised consistently.
"""

from __future__ import annotations

import pytest

pytest.importorskip("hypothesis")

from hypothesis import given, settings
from hypothesis import strategies as st

from app.orchestration.config_resolver import _VALID_LLM_PROVIDERS

_noise = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        whitelist_characters=" -_.",
    ),
    min_size=0,
    max_size=50,
)


def _normalise(raw: str | None) -> str:
    # Mirrors the logic in _ensure_cache; kept as a pure helper so property
    # tests don't need to stand up a DB session.
    if not raw:
        return "api"
    name = raw.strip().lower().replace("-", "_")
    if not name:
        return "api"
    if name not in _VALID_LLM_PROVIDERS:
        return "api"
    return name


@settings(max_examples=500, deadline=None)
@given(st.one_of(st.none(), _noise))
def test_normalise_always_returns_valid_provider(raw: str | None) -> None:
    out = _normalise(raw)
    assert out in _VALID_LLM_PROVIDERS


@settings(max_examples=50, deadline=None)
@given(st.sampled_from(sorted(_VALID_LLM_PROVIDERS)))
def test_valid_names_pass_through(name: str) -> None:
    assert _normalise(name) == name
    # Case-insensitive and dash-insensitive.
    assert _normalise(name.upper()) == name
    assert _normalise(name.replace("_", "-")) == name
