"""Cursor paste-per-action ``submit_analyze`` updates the source document.

Regression coverage for the bug where the Cursor LLM path persisted every
analysis artefact (ambiguities, contradictions, edge cases, tasks,
traceability) but never marked the source ``FSDocument`` as ``COMPLETE``.
The result was that the doc detail page stayed in ``PARSED`` forever and
the Build CTA was hidden, even though the analysis had clearly finished.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import FSDocument, FSDocumentStatus

_PAYLOAD = {
    "quality_score": {
        "overall": 88,
        "clarity": 85,
        "completeness": 90,
        "consistency": 88,
        "risks": [],
    },
    "ambiguities": [],
    "contradictions": [],
    "edge_cases": [],
    "tasks": [
        {
            "title": "Implement CRUD",
            "description": "Build todo CRUD endpoints.",
            "section_index": 0,
            "section_heading": "Spec",
            "depends_on": [],
            "acceptance_criteria": ["Can create"],
            "effort": "MEDIUM",
            "tags": ["backend"],
            "can_parallel": False,
        }
    ],
}


@pytest.mark.asyncio
async def test_cursor_submit_analyze_marks_doc_complete(client: AsyncClient, test_db):
    """``submit_analyze`` must transition status PARSED -> COMPLETE."""
    doc = FSDocument(
        id=uuid.uuid4(),
        filename="spec.md",
        original_text="# Spec\nBuild a todo app.",
        parsed_text="# Spec\nBuild a todo app.",
        status=FSDocumentStatus.PARSED,
        file_size=30,
        content_type="text/markdown",
    )
    test_db.add(doc)
    await test_db.commit()

    resp = await client.post(f"/api/cursor-tasks/analyze/{doc.id}")
    task_id = resp.json()["data"]["task_id"]
    await client.post(f"/api/cursor-tasks/{task_id}/claim")

    submit = await client.post(
        f"/api/cursor-tasks/{task_id}/submit/analyze",
        json={"payload": _PAYLOAD},
    )
    assert submit.status_code == 200, submit.text

    row = await test_db.execute(select(FSDocument).where(FSDocument.id == doc.id))
    refreshed = row.scalar_one()
    assert refreshed.status == FSDocumentStatus.COMPLETE, (
        "Cursor analyze submit must promote the document to COMPLETE so the Build CTA appears."
    )
    assert refreshed.analysis_stale is False


@pytest.mark.asyncio
async def test_cursor_submit_analyze_clears_stale_flag(client: AsyncClient, test_db):
    """A re-analysis on a COMPLETE+stale doc must clear ``analysis_stale``."""
    doc = FSDocument(
        id=uuid.uuid4(),
        filename="spec.md",
        original_text="# Spec",
        parsed_text="# Spec",
        status=FSDocumentStatus.COMPLETE,
        analysis_stale=True,
        file_size=10,
        content_type="text/markdown",
    )
    test_db.add(doc)
    await test_db.commit()

    resp = await client.post(f"/api/cursor-tasks/analyze/{doc.id}")
    task_id = resp.json()["data"]["task_id"]
    await client.post(f"/api/cursor-tasks/{task_id}/claim")

    submit = await client.post(
        f"/api/cursor-tasks/{task_id}/submit/analyze",
        json={"payload": _PAYLOAD},
    )
    assert submit.status_code == 200, submit.text

    row = await test_db.execute(select(FSDocument).where(FSDocument.id == doc.id))
    refreshed = row.scalar_one()
    assert refreshed.status == FSDocumentStatus.COMPLETE
    assert refreshed.analysis_stale is False
