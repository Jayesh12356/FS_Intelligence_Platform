"""Golden-diff test for every v2 prompt.

Records a short structural signature (name, role opening, mission,
constraint count, schema hash) and compares it against a committed JSON
baseline in ``golden/prompt_signatures.json``. Any uncommitted drift
causes this test to fail, so prompt changes are reviewed explicitly.

To update the baseline after an intentional prompt change::

    cd backend && PROMPT_EVAL_UPDATE=1 pytest tests/prompt_eval/test_golden.py

``PROMPT_EVAL_UPDATE=1`` is the only way to rewrite the file — never
edit ``prompt_signatures.json`` by hand.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from .test_structural import PROMPTS

GOLDEN_PATH = Path(__file__).parent / "golden" / "prompt_signatures.json"


def _signature_for(name: str, spec) -> dict:
    contract = spec.output_contract
    return {
        "name": name,
        "role_opening": spec.role.strip().split(".")[0][:120],
        "mission": spec.mission.strip(),
        "constraint_count": len(spec.constraints),
        "contract_shape": contract.shape.value if contract else None,
        "contract_hash": contract.schema_hash() if contract else None,
        "few_shot_count": len(spec.few_shot),
    }


def _current_signatures() -> dict[str, dict]:
    return {name: _signature_for(name, spec) for name, spec, _ in PROMPTS}


def _load_golden() -> dict[str, dict]:
    if not GOLDEN_PATH.exists():
        return {}
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _write_golden(data: dict[str, dict]) -> None:
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_prompt_signatures_match_golden() -> None:
    """Fail if any prompt drifted without a committed golden update."""
    current = _current_signatures()

    if os.getenv("PROMPT_EVAL_UPDATE") == "1":
        _write_golden(current)
        pytest.skip("Golden baseline rewritten (PROMPT_EVAL_UPDATE=1).")

    golden = _load_golden()

    if not golden:
        _write_golden(current)
        pytest.skip("No baseline found; initial golden written. Re-run the test.")

    missing = set(current) - set(golden)
    unexpected = set(golden) - set(current)
    assert not missing, f"New prompts missing from golden: {sorted(missing)}"
    assert not unexpected, f"Golden references prompts no longer present: {sorted(unexpected)}"

    drifted = []
    for name in sorted(current):
        if current[name] != golden[name]:
            drifted.append(
                {
                    "name": name,
                    "current": current[name],
                    "golden": golden[name],
                }
            )
    assert not drifted, (
        "Prompt signatures drifted from golden. Review diffs and re-run "
        "with PROMPT_EVAL_UPDATE=1 to accept:\n" + json.dumps(drifted, indent=2)
    )
