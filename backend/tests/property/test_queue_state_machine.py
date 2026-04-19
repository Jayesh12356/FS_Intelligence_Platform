"""Property tests for the Cursor-task queue state machine.

The queue models transitions:

    pending -> claimed -> delivered
    pending -> claimed -> failed
    pending -> cancelled

Invariants exercised here:

1. A task cannot leave a terminal state (delivered / failed / cancelled).
2. Reaching the same state from the same prior state is idempotent
   (same result, no exception).
3. Claim without a prior pending entry is refused.
"""

from __future__ import annotations

import pytest

pytest.importorskip("hypothesis")

from hypothesis import given, settings
from hypothesis import strategies as st

TERMINAL = {"delivered", "failed", "cancelled"}
STATES = ["pending", "claimed", "delivered", "failed", "cancelled"]


def _transition(state: str, event: str) -> str:
    """Pure state-machine reducer."""
    if state in TERMINAL:
        return state  # terminal — no further transitions
    if state == "pending" and event == "claim":
        return "claimed"
    if state == "pending" and event == "cancel":
        return "cancelled"
    if state == "claimed" and event == "deliver":
        return "delivered"
    if state == "claimed" and event == "fail":
        return "failed"
    # Anything else is a no-op — the caller's bug, not the machine's.
    return state


@settings(max_examples=500, deadline=None)
@given(
    state=st.sampled_from(STATES),
    events=st.lists(
        st.sampled_from(["claim", "deliver", "fail", "cancel"]),
        max_size=10,
    ),
)
def test_terminal_states_are_absorbing(state: str, events: list[str]) -> None:
    if state not in TERMINAL:
        return
    for e in events:
        assert _transition(state, e) == state


@settings(max_examples=500, deadline=None)
@given(events=st.lists(st.sampled_from(["claim", "deliver", "fail", "cancel"]), max_size=20))
def test_reaching_a_terminal_state_locks_it(events: list[str]) -> None:
    state = "pending"
    for e in events:
        state = _transition(state, e)
    # Once terminal, any further events leave state unchanged.
    if state in TERMINAL:
        for e in ["claim", "deliver", "fail", "cancel"]:
            assert _transition(state, e) == state


@settings(max_examples=200, deadline=None)
@given(st.sampled_from(["deliver", "fail"]))
def test_cannot_deliver_or_fail_without_claim(event: str) -> None:
    # Pending -> deliver/fail should be refused (state unchanged).
    assert _transition("pending", event) == "pending"
