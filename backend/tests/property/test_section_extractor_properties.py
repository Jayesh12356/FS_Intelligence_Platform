"""Property-based tests for ``app.parsers.section_extractor``.

Invariants:

1. ``extract_sections_from_text`` never raises on any printable unicode input.
2. Output is always a list (possibly empty).
3. Every returned section has a non-empty ``heading`` OR non-empty ``content``.
4. ``heading`` and ``content`` round-trip as strings.
"""

from __future__ import annotations

import pytest

pytest.importorskip("hypothesis")

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.parsers.section_extractor import extract_sections_from_text

# Restrict to printable unicode to avoid fuzzing against bugs that are
# external to the parser (e.g. system-level encoding limits).
_text_strategy = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        whitelist_characters="\n\r\t .,:;-_#=",
    ),
    min_size=0,
    max_size=2000,
)


@settings(
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(_text_strategy)
def test_extract_sections_never_raises(text: str) -> None:
    sections = extract_sections_from_text(text)
    assert isinstance(sections, list)
    for s in sections:
        # Either heading or content must carry signal; an empty-empty entry
        # means the extractor produced noise.
        heading = (getattr(s, "heading", "") or "").strip()
        content = (getattr(s, "content", "") or "").strip()
        assert heading or content, repr(s)


@settings(max_examples=50, deadline=None)
@given(st.integers(min_value=1, max_value=50))
def test_extract_sections_scales_linearly(n: int) -> None:
    """The parser should emit <= n sections for n numbered headings."""
    body = "\n".join(f"{i}. Heading {i}\nBody content for section {i}." for i in range(1, n + 1))
    sections = extract_sections_from_text(body)
    assert len(sections) <= n
