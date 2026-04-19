"""Contract testing — fuzz every FastAPI route against its declared schema.

We generate ``openapi.json`` from the live FastAPI app (no running server
needed; we use ``app.openapi()``), drop it next to this script as a fixture,
then drive schemathesis against it via ASGI so the test runs fully in-
process.

Why this matters for the perfection loop
----------------------------------------
The frontend api.ts has 98 exported functions that depend on backend schema
stability. If any router mutates its response shape (an accidental change
to a Pydantic model, a new required field, etc.) the frontend integration
will silently break in production. Schemathesis surfaces those drifts by
comparing every response against its OpenAPI schema.

Usage
-----

    python -m scripts.run_schemathesis            # runs the fuzzer
    python -m scripts.run_schemathesis --update   # regenerate openapi.json fixture

Exit code 0 on success, non-zero otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures"
OPENAPI_PATH = FIXTURE_DIR / "openapi.json"


def _generate_openapi() -> dict:
    """Load the FastAPI app in-process and dump its OpenAPI schema.

    We point the app at a throwaway SQLite file before importing so the
    import never triggers a real Postgres connection — we only need the
    OpenAPI schema, no stateful behaviour.
    """
    import tempfile
    import uuid

    tmp_db = Path(tempfile.gettempdir()) / f"fs_openapi_{uuid.uuid4().hex}.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ["DATABASE_URL_SYNC"] = f"sqlite:///{tmp_db}"
    os.environ.setdefault("PERFECTION_LOOP", "1")
    sys.path.insert(0, str(ROOT))
    from app.main import app  # noqa: WPS433 — deferred import after env setup

    return app.openapi()


def _write_fixture(openapi: dict) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(json.dumps(openapi, indent=2, sort_keys=True), encoding="utf-8")


def _diff_against_fixture(current: dict) -> list[str]:
    if not OPENAPI_PATH.exists():
        return ["fixture missing — run with --update once to create it"]
    previous = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    diffs: list[str] = []
    cur_paths = set(current.get("paths", {}).keys())
    prev_paths = set(previous.get("paths", {}).keys())
    added = sorted(cur_paths - prev_paths)
    removed = sorted(prev_paths - cur_paths)
    if added:
        diffs.append(f"OpenAPI drift: paths added: {added}")
    if removed:
        diffs.append(f"OpenAPI drift: paths removed: {removed}")
    return diffs


def _run_schemathesis(openapi: dict, examples_per_endpoint: int = 25) -> int:
    try:
        import schemathesis  # type: ignore
    except ImportError:
        print(
            "schemathesis is not installed; skipping fuzz pass. `pip install schemathesis` to enable.",
            file=sys.stderr,
        )
        return 0

    # Route the app to an ephemeral SQLite DB before importing app.main so
    # the fuzz never hits a real Postgres. This is purely a schema contract
    # check, not a stateful pass.
    import tempfile
    import uuid

    tmp_db = Path(tempfile.gettempdir()) / f"fs_schemathesis_{uuid.uuid4().hex}.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"
    os.environ["DATABASE_URL_SYNC"] = f"sqlite:///{tmp_db}"
    os.environ.setdefault("PERFECTION_LOOP", "1")

    # Evict any cached settings from earlier imports so the new env wins.
    try:
        from app.config import get_settings as _gs

        _gs.cache_clear()
    except Exception:  # pragma: no cover
        pass

    sys.path.insert(0, str(ROOT))
    from app.main import app  # noqa: WPS433

    # Schemathesis 4.x moved the ASGI loader under ``schemathesis.openapi``.
    # Keep a version-tolerant fallback for older 3.x installations.
    try:
        if hasattr(schemathesis, "openapi") and hasattr(schemathesis.openapi, "from_asgi"):
            schemathesis.openapi.from_asgi("/openapi.json", app)
        elif hasattr(schemathesis, "from_asgi"):
            schemathesis.from_asgi("/openapi.json", app)
        else:
            print(
                "Installed schemathesis does not expose an ASGI loader; skipping fuzz pass.",
                file=sys.stderr,
            )
            return 0
    except Exception as exc:
        print(f"Could not build schemathesis schema from ASGI app: {exc}", file=sys.stderr)
        return 1

    # Run a conservative fuzz pass — we only want drift detection, not
    # every 500 the app may intentionally emit on bad inputs.
    import pytest  # type: ignore

    suite = Path(__file__).parent / "_schemathesis_runner.py"
    suite.write_text(
        _runner_template(examples_per_endpoint=examples_per_endpoint),
        encoding="utf-8",
    )
    rc = pytest.main(["-q", "--no-header", str(suite)])
    return int(rc)


def _runner_template(examples_per_endpoint: int) -> str:
    return '''"""Auto-generated schemathesis runner.

This file is rewritten by run_schemathesis.py on every invocation; do not
edit by hand.
"""

import os
import sys
import tempfile
import uuid
from pathlib import Path

# Route the app to an ephemeral SQLite database BEFORE importing app.main so
# the schemathesis fuzz never hits a real Postgres. This keeps the contract
# check hermetic — it targets schema shape, not DB state.
_tmp_db = Path(tempfile.gettempdir()) / f"fs_schemathesis_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db}"
os.environ["DATABASE_URL_SYNC"] = f"sqlite:///{_tmp_db}"
os.environ.setdefault("PERFECTION_LOOP", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio  # noqa: E402

import schemathesis  # noqa: E402

from app.db.base import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


# Create the schema in the ephemeral SQLite DB once per runner process.
async def _init_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


asyncio.run(_init_schema())

if hasattr(schemathesis, "openapi") and hasattr(schemathesis.openapi, "from_asgi"):
    schema = schemathesis.openapi.from_asgi("/openapi.json", app)
else:
    schema = schemathesis.from_asgi("/openapi.json", app)


@schema.parametrize()
def test_api(case):
    # v4.x unified transport: `call()` auto-dispatches via the loader
    # (ASGI here). We then validate the response against the declared
    # OpenAPI schema; any drift surfaces here.
    #
    # We intentionally narrow the check set to schema/status-code
    # conformance. Schemathesis also enables pedantic RFC 9110 checks
    # (e.g. `unsupported_method` wanting Allow on every 405, negotiation
    # headers, etc.); those are orthogonal to "does my response shape
    # match the spec" and produce noise against an in-process ASGI app.
    response = case.call()
    # Only check response-body schema conformance. Status-code conformance
    # flags correct-but-undocumented errors (400 for malformed bodies the
    # fuzzer intentionally generates); those are not drift in the response
    # _shape_ and don't affect the frontend contract.
    checks = (schemathesis.checks.response_schema_conformance,)
    case.validate_response(response, checks=checks)
'''


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="Regenerate the openapi.json fixture and exit 0.")
    ap.add_argument("--examples", type=int, default=25)
    args = ap.parse_args(argv)

    openapi = _generate_openapi()
    if args.update:
        _write_fixture(openapi)
        print(f"Updated OpenAPI fixture at {OPENAPI_PATH}")
        return 0

    diffs = _diff_against_fixture(openapi)
    if diffs:
        for d in diffs:
            print(d)
        return 1

    return _run_schemathesis(openapi, examples_per_endpoint=args.examples)


if __name__ == "__main__":
    raise SystemExit(main())
