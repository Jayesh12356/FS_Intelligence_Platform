"""COMPLETE-status invariants for FSDocument.

User contract (0.4.x):
* Once an analysis run finishes, ``FSDocument.status`` is ``COMPLETE``
  and **must stay that way** until explicit deletion. Refining the spec,
  accepting an edge case, accepting a contradiction, or reverting to a
  previous version should keep ``status=COMPLETE`` and merely flip
  ``analysis_stale=True`` so the UI can prompt for a re-analyze.
* Older / imported documents that landed in ``PARSED`` despite having
  full analysis rows attached (e.g. ``970889b8-…``) are auto-healed to
  ``COMPLETE`` the first time ``GET /api/fs/{id}`` is called.

These tests pin down those invariants so future refactors don't
regress the Build CTA visibility on the document detail page.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import (
    AmbiguitySeverity,
    EdgeCaseGapDB,
    FSDocument,
    FSDocumentStatus,
    FSTaskDB,
    FSVersion,
    EffortLevel,
    TaskStatus,
)


_BASE_TEXT = (
    "# Spec\n\n"
    "## Goals\n"
    "Tiny CRUD app.\n\n"
    "## API\n"
    "GET /things returns a list.\n"
)


async def _seed_doc(test_db, *, status: FSDocumentStatus, stale: bool = False) -> FSDocument:
    doc = FSDocument(
        id=uuid.uuid4(),
        filename="spec.md",
        original_text=_BASE_TEXT,
        parsed_text=_BASE_TEXT,
        status=status,
        analysis_stale=stale,
        file_size=len(_BASE_TEXT),
        content_type="text/markdown",
    )
    test_db.add(doc)
    await test_db.commit()
    await test_db.refresh(doc)
    return doc


async def _seed_task(test_db, doc_id: uuid.UUID) -> FSTaskDB:
    task = FSTaskDB(
        id=uuid.uuid4(),
        fs_id=doc_id,
        task_id=uuid.uuid4().hex,
        title="Build the thing",
        description="Implement the tiny CRUD app from the spec.",
        section_index=0,
        section_heading="Goals",
        depends_on=[],
        acceptance_criteria=["passes smoke"],
        effort=EffortLevel.MEDIUM,
        tags=[],
        status=TaskStatus.PENDING,
        order=0,
        can_parallel=False,
    )
    test_db.add(task)
    await test_db.commit()
    return task


# ── Auto-heal on GET ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_document_auto_heals_parsed_with_tasks_to_complete(
    client: AsyncClient, test_db
):
    """A PARSED doc that already has tasks must be promoted on first GET."""
    doc = await _seed_doc(test_db, status=FSDocumentStatus.PARSED)
    doc_id = doc.id
    await _seed_task(test_db, doc_id)

    resp = await client.get(f"/api/fs/{doc_id}")
    assert resp.status_code == 200, resp.text

    body = resp.json()["data"]
    assert body["status"] == "COMPLETE", (
        "GET /api/fs/{id} should auto-heal PARSED docs that already have "
        "analysis rows so the Build CTA appears without manual re-analysis."
    )
    assert body["analysis_stale"] is True

    # Persisted in DB so subsequent reads keep COMPLETE.
    test_db.expire_all()
    refreshed = (
        await test_db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    ).scalar_one()
    assert refreshed.status == FSDocumentStatus.COMPLETE
    assert refreshed.analysis_stale is True


@pytest.mark.asyncio
async def test_get_document_does_not_promote_pristine_parsed(
    client: AsyncClient, test_db
):
    """PARSED doc without any analysis rows must stay PARSED."""
    doc = await _seed_doc(test_db, status=FSDocumentStatus.PARSED)
    doc_id = doc.id

    resp = await client.get(f"/api/fs/{doc_id}")
    assert resp.status_code == 200, resp.text

    body = resp.json()["data"]
    assert body["status"] == "PARSED"
    assert body["analysis_stale"] is False


# ── Revert keeps COMPLETE ─────────────────────────────────────


@pytest.mark.asyncio
async def test_revert_to_version_keeps_complete(client: AsyncClient, test_db):
    """Reverting a COMPLETE doc to an earlier version keeps status COMPLETE
    and only flips ``analysis_stale=True``."""
    doc = await _seed_doc(test_db, status=FSDocumentStatus.COMPLETE)
    doc_id = doc.id

    version = FSVersion(
        id=uuid.uuid4(),
        fs_id=doc_id,
        version_number=1,
        parsed_text="# Spec (old)\n\n## Goals\nOriginal text.\n",
    )
    test_db.add(version)
    await test_db.commit()
    version_id = version.id

    resp = await client.post(f"/api/fs/{doc_id}/versions/{version_id}/revert")
    assert resp.status_code == 200, resp.text

    test_db.expire_all()
    refreshed = (
        await test_db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    ).scalar_one()
    assert refreshed.status == FSDocumentStatus.COMPLETE, (
        "Revert must NOT demote a COMPLETE doc — that hides the Build CTA."
    )
    assert refreshed.analysis_stale is True
    assert refreshed.parsed_text == "# Spec (old)\n\n## Goals\nOriginal text.\n"


@pytest.mark.asyncio
async def test_revert_on_parsed_doc_still_demotes_to_parsed(
    client: AsyncClient, test_db
):
    """Reverting a doc that never reached COMPLETE keeps it PARSED."""
    doc = await _seed_doc(test_db, status=FSDocumentStatus.PARSED)
    doc_id = doc.id

    version = FSVersion(
        id=uuid.uuid4(),
        fs_id=doc_id,
        version_number=1,
        parsed_text="# Spec (old)\n",
    )
    test_db.add(version)
    await test_db.commit()
    version_id = version.id

    resp = await client.post(f"/api/fs/{doc_id}/versions/{version_id}/revert")
    assert resp.status_code == 200, resp.text

    test_db.expire_all()
    refreshed = (
        await test_db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    ).scalar_one()
    assert refreshed.status == FSDocumentStatus.PARSED
    assert refreshed.analysis_stale is False


# ── Accept-edge-case keeps COMPLETE ───────────────────────────


@pytest.mark.asyncio
async def test_accept_edge_case_keeps_complete(client: AsyncClient, test_db):
    """Accepting an edge case suggestion on a COMPLETE doc must preserve
    the COMPLETE status and flip ``analysis_stale=True``."""
    doc = await _seed_doc(test_db, status=FSDocumentStatus.COMPLETE)
    doc_id = doc.id

    edge = EdgeCaseGapDB(
        id=uuid.uuid4(),
        fs_id=doc_id,
        section_index=1,
        section_heading="API",
        scenario_description="Empty list response is undefined.",
        impact=AmbiguitySeverity.MEDIUM,
        suggested_addition="Return an empty array `[]` when no things exist.",
        resolved=False,
    )
    test_db.add(edge)
    await test_db.commit()
    edge_id = edge.id

    resp = await client.post(f"/api/fs/{doc_id}/edge-cases/{edge_id}/accept")
    assert resp.status_code == 200, resp.text

    test_db.expire_all()
    refreshed = (
        await test_db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    ).scalar_one()
    assert refreshed.status == FSDocumentStatus.COMPLETE
    assert refreshed.analysis_stale is True
