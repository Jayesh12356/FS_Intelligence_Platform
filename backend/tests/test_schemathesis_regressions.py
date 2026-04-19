"""Regression tests for production bugs surfaced by the Schemathesis fuzzer.

Each test below pins down a real defect that escaped to production before the
Phase-1 perfection sweep. They exist *not* to duplicate Schemathesis
coverage but to:

1. Run on every commit (Schemathesis is a 20-minute job),
2. Document the exact contract each fix preserves so future refactors don't
   silently regress them.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


# ── 1. Naive-datetime serialization on POST endpoints ─────────────────
#
# Bug: Endpoints that ``await db.refresh(obj)`` used the SQLAlchemy
# ``refresh`` event path, which our normalizer did NOT cover. SQLite
# returned naive datetimes, so ``created_at`` was emitted as
# ``"2026-04-18T10:55:36.657891"`` (no Z / no offset) — violating the
# OpenAPI contract that declared ``format: "date-time"`` (RFC 3339,
# tz required).
#
# Fix: ``app/db/base.py`` now wires both ``load`` and ``refresh`` events
# on ``Base`` so every datetime crossing the ORM boundary is UTC-aware
# regardless of whether it came from a fresh SELECT, a relationship
# lazy-load, or an explicit refresh after INSERT.
@pytest.mark.asyncio
async def test_post_project_returns_tz_aware_datetimes(client):
    """POST /api/projects must emit timezone-aware created_at/updated_at.

    Reproduction (pre-fix): the response body contained
    ``"created_at": "2026-04-18T10:55:36.657891"`` — naive, breaking the
    OpenAPI ``format: date-time`` declaration.
    """
    response = await client.post(
        "/api/projects",
        json={"name": "tz-regression-project", "description": "regression"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    for field in ("created_at", "updated_at"):
        value = payload[field]
        # RFC 3339 / ISO 8601 timezone marker — either +HH:MM or Z suffix
        assert value.endswith("Z") or "+" in value or value.endswith("+00:00"), (
            f"{field}={value!r} is naive; expected timezone suffix"
        )
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None, f"{field}={value!r} parsed without tzinfo"


# ── 2. Unbounded pagination overflows SQLite INTEGER ──────────────────
#
# Bug: ``GET /api/activity-log?offset=9223372036854775808`` (== 2**63)
# crashed the server with ``OverflowError: Python int too large to
# convert to SQLite INTEGER`` because the FastAPI Query had only
# ``ge=0`` — no upper bound. Postgres BIGINT would survive, but the
# right fix is to bound the API contract, not paper over the dialect.
#
# Fix: ``Query(ge=0, le=2**31 - 1)`` on every paginated route
# (``activity_router``, ``fs_router``, ``code_router``).
@pytest.mark.asyncio
async def test_activity_log_rejects_int_overflow_offset(client):
    response = await client.get("/api/activity-log", params={"offset": 2**63})
    # FastAPI/Pydantic returns 422 for out-of-range query params; previously
    # this returned 500 with an OverflowError leaked through.
    assert response.status_code == 422, response.text
    body = response.json()
    assert "offset" in str(body), body


@pytest.mark.asyncio
async def test_fs_list_rejects_int_overflow_offset(client):
    response = await client.get("/api/fs/", params={"offset": 2**63})
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_code_uploads_rejects_int_overflow_offset(client):
    response = await client.get("/api/code/uploads", params={"offset": 2**63})
    assert response.status_code == 422, response.text


# ── 3. Unvalidated UUID in idea/guided endpoint ───────────────────────
#
# Bug: ``POST /api/idea/guided`` accepted any string as ``session_id``
# and called ``uuid.UUID(req.session_id)`` without try/except. Sending
# ``{"session_id": "0", "step": 1}`` raised ``ValueError: badly formed
# hexadecimal UUID string``, which Starlette converted into a 500
# Internal Server Error — exposing an implementation detail and
# violating the principle "client error → 4xx".
#
# Fix: wrap the parse in ``try/except (ValueError, AttributeError,
# TypeError)`` and raise ``HTTPException(400)`` with a helpful message.
@pytest.mark.asyncio
async def test_idea_guided_returns_400_for_invalid_session_id(client):
    response = await client.post(
        "/api/idea/guided",
        json={"step": 1, "session_id": "0"},  # not a UUID
    )
    # Pre-fix: 500 (ValueError); post-fix: 400 with detail
    assert response.status_code == 400, response.text
    body = response.json()
    assert "session_id" in str(body).lower()


# ── 4. Naive-datetime stamp from default=lambda: datetime.now(UTC) ─────
#
# Defense-in-depth: even though the column defaults are tz-aware, the
# ``refresh`` event still fires immediately after INSERT to normalize
# anything SQLite stripped on round-trip. Verify the listener actually
# upgrades a naive value to UTC.
def test_normalize_instance_datetimes_promotes_naive_to_utc():
    from app.db.base import _normalize_instance_datetimes
    from app.db.models import FSProject

    project = FSProject(
        id=__import__("uuid").uuid4(),
        name="naive-dt-test",
        description=None,
        created_at=datetime(2024, 1, 1, 12, 0, 0),  # naive!
        updated_at=datetime(2024, 1, 1, 12, 0, 0),  # naive!
    )
    _normalize_instance_datetimes(project)
    assert project.created_at.tzinfo == UTC
    assert project.updated_at.tzinfo == UTC
