"""Unit tests for the per-run token accounting helpers.

These guard the ``live_smoke`` telemetry: if the increments silently
break (e.g. a refactor removes the ``add_to_token_accounting`` call),
the smoke driver would always report ``tokens=0`` and we would lose
visibility into real regressions where a single small spec balloons.
No hard budget is enforced — the counter is informational only.
"""

from __future__ import annotations

from app.llm.client import (
    add_to_token_accounting,
    get_last_run_token_count,
    reset_token_accounting,
)


def test_reset_zeroes_counter():
    add_to_token_accounting(123, 456)
    assert get_last_run_token_count() > 0
    reset_token_accounting()
    assert get_last_run_token_count() == 0


def test_increments_accumulate_input_plus_output():
    reset_token_accounting()
    add_to_token_accounting(10, 5)
    add_to_token_accounting(2, 3)
    assert get_last_run_token_count() == 20


def test_negative_values_are_ignored():
    reset_token_accounting()
    add_to_token_accounting(-1, 5)
    add_to_token_accounting(5, -1)
    assert get_last_run_token_count() == 0


def test_state_is_thread_safe_under_concurrency():
    """Many concurrent increments must sum without a lost-update race."""
    import threading

    reset_token_accounting()
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        for _ in range(1000):
            add_to_token_accounting(1, 1)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Each worker contributes 2*1000 tokens; 8 workers => 16000 total.
    assert get_last_run_token_count() == 16_000
