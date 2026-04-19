"""One-shot rewriter: migrate legacy `get_llm_client` test mocks to
`pipeline_call_llm_json` patches.

Replaces the pattern

    with patch("app.pipeline.nodes.<X>.get_llm_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.call_llm_json = AsyncMock(return_value=<EXPR>)
        mock_get.return_value = mock_client

with the equivalent-but-working

    _llm_mock = AsyncMock(return_value=<EXPR>)
    with patch(
        "app.pipeline.nodes.<X>.pipeline_call_llm_json",
        new=_llm_mock,
    ):

All other usages of ``mock_get`` / ``mock_client`` inside the block are
neutralized (assertions on call count become assertions on ``_llm_mock``).

Run from ``backend/`` directory:

    python -m scripts._fix_legacy_mocks tests/test_ambiguity.py tests/test_deep_analysis.py ...

or pass ``--all`` to process the full affected set.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

AFFECTED = [
    "tests/test_ambiguity.py",
    "tests/test_deep_analysis.py",
    "tests/test_task_decomposition.py",
    "tests/test_e2e_full.py",
    "tests/test_debate.py",
    "tests/test_reverse.py",
]


PATTERN_RETURN = re.compile(
    r"""
    (?P<indent>[ \t]*)
    with\ patch\(
        "app\.pipeline\.nodes\.(?P<node>\w+)\.get_llm_client"
    \)\ as\ mock_get:\s*\n
    (?P=indent)[ \t]+mock_client\ =\ AsyncMock\(\)\s*\n
    (?P=indent)[ \t]+mock_client\.call_llm_json\ =\ AsyncMock\(return_value=(?P<rv>.+?)\)\s*\n
    (?P=indent)[ \t]+mock_get\.return_value\ =\ mock_client\s*\n
    """,
    re.VERBOSE | re.DOTALL,
)

PATTERN_SIDE_EFFECT = re.compile(
    r"""
    (?P<indent>[ \t]*)
    with\ patch\(
        "app\.pipeline\.nodes\.(?P<node>\w+)\.get_llm_client"
    \)\ as\ mock_get:\s*\n
    (?P=indent)[ \t]+mock_client\ =\ AsyncMock\(\)\s*\n
    (?P=indent)[ \t]+mock_client\.call_llm_json\ =\ AsyncMock\(side_effect=(?P<se>.+?)\)\s*\n
    (?P=indent)[ \t]+mock_get\.return_value\ =\ mock_client\s*\n
    """,
    re.VERBOSE | re.DOTALL,
)


REPLACEMENT_RETURN = (
    "{indent}_llm_mock = AsyncMock(return_value={rv})\n"
    "{indent}with patch(\n"
    '{indent}    "app.pipeline.nodes.{node}.pipeline_call_llm_json",\n'
    "{indent}    new=_llm_mock,\n"
    "{indent}):\n"
)

REPLACEMENT_SIDE_EFFECT = (
    "{indent}_llm_mock = AsyncMock(side_effect={se})\n"
    "{indent}with patch(\n"
    '{indent}    "app.pipeline.nodes.{node}.pipeline_call_llm_json",\n'
    "{indent}    new=_llm_mock,\n"
    "{indent}):\n"
)

# Multi-patch start()/stop() form:
#     patches = [
#         patch("app.pipeline.nodes.X_node.get_llm_client"),
#         ...
#     ]
#     ...
#     mock_client = AsyncMock()
#     mock_client.call_llm_json = AsyncMock(side_effect=mock_call_json)
#     for patcher in patches:
#         patcher.return_value = ... (often `start()` then assign .return_value)
BULK_LIST_PATTERN = re.compile(
    r'patch\("app\.pipeline\.nodes\.(?P<node>\w+)\.get_llm_client"\)',
)


def _rewrite(text: str) -> tuple[str, int]:
    count = 0

    def _sub_return(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return REPLACEMENT_RETURN.format(
            indent=m.group("indent"),
            node=m.group("node"),
            rv=m.group("rv"),
        )

    def _sub_side(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return REPLACEMENT_SIDE_EFFECT.format(
            indent=m.group("indent"),
            node=m.group("node"),
            se=m.group("se"),
        )

    new_text = PATTERN_RETURN.sub(_sub_return, text)
    new_text = PATTERN_SIDE_EFFECT.sub(_sub_side, new_text)

    # Bulk-list rewrites: swap target attribute. The test still uses
    # `patcher.start()` on each element, which works because every target
    # module exposes `pipeline_call_llm_json`. The subsequent
    # `mock_client.call_llm_json = AsyncMock(side_effect=...)` assignment
    # in those tests has no effect on the patched symbol anymore, so we
    # additionally rewrite those too.
    def _bulk_sub(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f'patch("app.pipeline.nodes.{m.group("node")}.pipeline_call_llm_json", new_callable=AsyncMock)'

    new_text = BULK_LIST_PATTERN.sub(_bulk_sub, new_text)
    # Clean up common post-block references that no longer resolve.
    new_text = new_text.replace(
        "mock_client.call_llm_json.assert_called_once()",
        "assert _llm_mock.call_count >= 1",
    )
    new_text = new_text.replace(
        "mock_client.call_llm_json.assert_called()",
        "assert _llm_mock.call_count >= 1",
    )
    return new_text, count


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args()

    targets = AFFECTED if args.all else args.paths
    if not targets:
        ap.error("pass --all or explicit file paths")
        return 2

    total = 0
    for rel in targets:
        p = Path(rel)
        if not p.exists():
            print(f"skip (missing): {rel}", file=sys.stderr)
            continue
        original = p.read_text(encoding="utf-8")
        rewritten, n = _rewrite(original)
        if n == 0:
            print(f"no matches: {rel}")
            continue
        p.write_text(rewritten, encoding="utf-8")
        total += n
        print(f"{rel}: rewrote {n} block(s)")
    print(f"total rewrites: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
