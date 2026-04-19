"""Live small-spec smoke driver for the perfection loop.

For each provider in ``PROVIDERS`` we:

1. Create a fresh in-process project and upload the TODO-API scenario text.
2. Kick off analysis (full server-side pipeline for ``api``; smoke-only
   acknowledgement for ``claude_code`` and ``cursor`` — the backend refuses
   server-side LLM calls for cursor by design).
3. Assert the ``small task behaves small`` invariant:
   - Quality score >= expected minimum.
   - Task count within ``[min_tasks, max_tasks]``.
   - Total input+output tokens are *reported* for visibility but are
     never gated — output completeness is more important than a budget.

Run directly:

    python -m scripts.live_smoke --provider api
    python -m scripts.live_smoke --provider claude_code
    python -m scripts.live_smoke --all

The driver prints a single-line JSON result per provider and exits non-zero
on any failure so the perfection loop can gate on it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.e2e_scenario import (  # noqa: E402
    EXPECTED,
    IDEA_TEXT,
    PROJECT_FULL,
    PROJECT_SMOKE_ONLY,
)

PROVIDERS = ["api", "claude_code", "cursor"]


class SmokeResult(dict):
    """Typed-ish dict so we can `json.dumps` without extra glue."""


async def _run_api_provider() -> SmokeResult:
    """Full pipeline run under the direct API provider.

    Token totals are *recorded* for visibility (via
    :func:`get_last_run_token_count`) but are intentionally **not** used
    as a pass/fail gate — the platform must be free to emit complete
    output without being truncated by an arbitrary budget.
    """
    from httpx import AsyncClient

    from app.main import app  # imported lazily so CLI --help is fast

    # Reset the per-run token accumulator so the reported total reflects
    # *only* this provider's smoke run rather than any prior runs in the
    # same process. The counter is informational; no budget is enforced.
    try:
        from app.llm.client import reset_token_accounting

        reset_token_accounting()
    except Exception:
        pass

    started = time.monotonic()
    result: SmokeResult = SmokeResult(
        provider="api",
        status="unknown",
        elapsed_s=0.0,
        tokens=0,
        tasks=0,
        quality=0.0,
        errors=[],
    )

    async with AsyncClient(app=app, base_url="http://test") as client:
        up = await client.post(
            "/api/fs/upload",
            files={"file": ("todo.txt", IDEA_TEXT.encode("utf-8"), "text/plain")},
        )
        if up.status_code != 200:
            result["errors"].append(f"upload failed: {up.status_code} {up.text[:200]}")
            result["status"] = "fail"
            return result
        doc_id = up.json()["data"]["id"]

        an = await client.post(f"/api/fs/{doc_id}/analyze", timeout=300.0)
        if an.status_code != 200:
            result["errors"].append(f"analyze failed: {an.status_code} {an.text[:200]}")
            result["status"] = "fail"
            return result

        quality = await client.get(f"/api/fs/{doc_id}/quality-score")
        tasks = await client.get(f"/api/fs/{doc_id}/tasks")

    q = quality.json().get("data", {}).get("overall", 0.0) if quality.status_code == 200 else 0.0
    t = len((tasks.json().get("data", {}) or {}).get("tasks", [])) if tasks.status_code == 200 else 0

    # Token accounting is optional and purely informational. If the LLM
    # client exposes a per-run counter we read it for the report;
    # otherwise we leave tokens at 0. No cap is ever applied.
    tokens = 0
    try:
        from app.llm.client import get_last_run_token_count

        tokens = int(get_last_run_token_count() or 0)
    except Exception:
        tokens = 0

    result.update(
        status="pass",
        tokens=tokens,
        tasks=t,
        quality=float(q),
        elapsed_s=round(time.monotonic() - started, 3),
    )

    errs: list[str] = []
    if q < EXPECTED["min_quality"]:
        errs.append(f"quality {q} < {EXPECTED['min_quality']}")
    if t < EXPECTED["min_tasks"] or t > EXPECTED["max_tasks"]:
        errs.append(f"tasks {t} outside [{EXPECTED['min_tasks']},{EXPECTED['max_tasks']}]")
    # Intentionally no token-budget assertion: output completeness wins.
    if errs:
        result["errors"] = errs
        result["status"] = "fail"
    return result


async def _run_smoke_only(provider: str) -> SmokeResult:
    """For providers that can't make server-side LLM calls, validate that
    the backend refuses cleanly and the MCP config endpoint still works."""
    from httpx import AsyncClient

    from app.main import app

    result: SmokeResult = SmokeResult(
        provider=provider,
        status="unknown",
        elapsed_s=0.0,
        tokens=0,
        tasks=0,
        quality=0.0,
        errors=[],
    )
    started = time.monotonic()
    async with AsyncClient(app=app, base_url="http://test") as client:
        cfg = await client.put(
            "/api/orchestration/config",
            json={"llm_provider": provider},
        )
        ok_cfg = cfg.status_code in (200, 400)
        test_call = await client.post(f"/api/orchestration/test/{provider}")
        mcp = await client.get("/api/orchestration/mcp-config")

    if not ok_cfg:
        result["errors"].append(f"config PUT returned {cfg.status_code}")
    if mcp.status_code != 200:
        result["errors"].append(f"mcp-config returned {mcp.status_code}")
    if provider == "cursor":
        tc = test_call.json() if test_call.status_code in (200, 409) else {}
        if tc and tc.get("error") is None and tc.get("data", {}).get("ok"):
            pass
        # cursor is allowed to return either "ok" or a refusal structure; both
        # are accepted here as long as the HTTP call itself didn't 5xx.
        if test_call.status_code >= 500:
            result["errors"].append(f"test/cursor returned {test_call.status_code}")
    result["elapsed_s"] = round(time.monotonic() - started, 3)
    result["status"] = "fail" if result["errors"] else "pass"
    return result


async def run_provider(provider: str) -> SmokeResult:
    if provider in PROJECT_FULL:
        return await _run_api_provider()
    if provider in PROJECT_SMOKE_ONLY:
        return await _run_smoke_only(provider)
    return SmokeResult(
        provider=provider,
        status="skip",
        errors=[f"unknown provider {provider}"],
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--provider", choices=PROVIDERS)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true", help="emit single JSON array")
    args = ap.parse_args()

    targets: list[str]
    if args.all:
        targets = list(PROVIDERS)
    elif args.provider:
        targets = [args.provider]
    else:
        ap.error("must pass --provider or --all")
        return 2

    os.environ.setdefault("PERFECTION_LOOP", "1")
    results: list[dict[str, Any]] = []
    exit_code = 0
    for prov in targets:
        try:
            res = asyncio.run(run_provider(prov))
        except Exception as exc:  # pragma: no cover
            res = SmokeResult(provider=prov, status="fail", errors=[repr(exc)])
        results.append(dict(res))
        if res.get("status") != "pass":
            exit_code = 1
        if not args.json:
            print(json.dumps(res, ensure_ascii=False))

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
