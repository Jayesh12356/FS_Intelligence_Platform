"""Refining a COMPLETE document must keep status=COMPLETE + flip stale=True.

Before 0.4.x, every refinement entrypoint hard-reset the doc to PARSED via
``_persist_refined_version``. That made the Build CTA disappear from the
detail page and forced an awkward ``?autoAnalyze=1`` workaround on the
frontend. The new contract is:

* status stays ``COMPLETE`` (Build CTA stays visible)
* ``analysis_stale`` flips to ``True`` so the UI surfaces a "re-analyze
  to refresh metrics" banner
* a fresh ``analyze`` run resets ``analysis_stale`` to ``False``

A document that was still ``PARSED`` at the time of refinement keeps the
``analysis_stale=False`` default — there is nothing to mark as stale.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import FSDocument, FSDocumentStatus

_REFINED = "# Spec (refined)\n\n## Goals\nBuild a tiny todo app that supports create / list / delete.\n"


async def _create_doc(test_db, *, status: FSDocumentStatus, stale: bool = False) -> FSDocument:
    doc = FSDocument(
        id=uuid.uuid4(),
        filename="spec.md",
        original_text="# Spec\nBuild a vague thing.",
        parsed_text="# Spec\nBuild a vague thing.",
        status=status,
        analysis_stale=stale,
        file_size=40,
        content_type="text/markdown",
    )
    test_db.add(doc)
    await test_db.commit()
    return doc


@pytest.mark.asyncio
async def test_refine_accept_keeps_complete_marks_stale(client: AsyncClient, test_db):
    doc = await _create_doc(test_db, status=FSDocumentStatus.COMPLETE)

    resp = await client.post(
        f"/api/fs/{doc.id}/refine/accept",
        json={"refined_text": _REFINED},
    )
    assert resp.status_code == 200, resp.text

    row = await test_db.execute(select(FSDocument).where(FSDocument.id == doc.id))
    refreshed = row.scalar_one()
    assert refreshed.status == FSDocumentStatus.COMPLETE, (
        "refine/accept must NOT demote a previously COMPLETE doc to PARSED "
        "— that hides the Build CTA on the detail page."
    )
    assert refreshed.analysis_stale is True
    # ``_persist_refined_version`` strips trailing whitespace before storing.
    assert refreshed.parsed_text == _REFINED.rstrip()


@pytest.mark.asyncio
async def test_refine_on_parsed_doc_does_not_set_stale(client: AsyncClient, test_db):
    doc = await _create_doc(test_db, status=FSDocumentStatus.PARSED)

    resp = await client.post(
        f"/api/fs/{doc.id}/refine/accept",
        json={"refined_text": _REFINED},
    )
    assert resp.status_code == 200, resp.text

    row = await test_db.execute(select(FSDocument).where(FSDocument.id == doc.id))
    refreshed = row.scalar_one()
    # A PARSED doc has no analysis to be stale against; status stays as
    # ``PARSED`` and the stale flag stays ``False``.
    assert refreshed.status == FSDocumentStatus.PARSED
    assert refreshed.analysis_stale is False
