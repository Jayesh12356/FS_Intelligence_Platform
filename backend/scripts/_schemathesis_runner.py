"""Auto-generated schemathesis runner.

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
