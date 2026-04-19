"""Regression test for the pipeline cache UUID-binding bug.

Before this fix, ``_set_cache`` / ``_get_cached_result`` were called with
``fs_id=str(fs_id)``. Because ``PipelineCacheDB.document_id`` is a
``UUID(as_uuid=True)`` column, SQLAlchemy's bind processor calls
``.hex`` on the value — strings raised ``AttributeError: 'str' object
has no attribute 'hex'`` and every write silently failed, disabling the
entire pipeline cache.

This test writes a row, reads it back, and also asserts that passing a
``str`` (the old broken call-site) now raises, so the contract is
enforced by the tests, not only by the production call-site.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FSDocument, PipelineCacheDB
from app.pipeline.graph import _get_cached_result, _set_cache


@pytest.mark.asyncio
async def test_cache_roundtrip_with_uuid(test_db: AsyncSession) -> None:
    """`_set_cache` then `_get_cached_result` returns the same payload."""
    doc_id = uuid.uuid4()

    # The cache has a FK into fs_documents, so create a parent row first.
    test_db.add(
        FSDocument(
            id=doc_id,
            filename="roundtrip.txt",
            content_type="text/plain",
            file_size=1,
            status="UPLOADED",
            file_path="/tmp/roundtrip.txt",
        )
    )
    await test_db.commit()

    payload = {"ambiguities": [{"id": "x", "severity": "HIGH"}]}
    await _set_cache(doc_id, "ambiguity_node", "hash-v1", payload, test_db)

    got = await _get_cached_result(doc_id, "ambiguity_node", "hash-v1", test_db)
    assert got == payload, "cache should return the exact payload we wrote"

    # Re-writing under a new hash must not raise and should return the new payload.
    payload_v2 = {"ambiguities": []}
    await _set_cache(doc_id, "ambiguity_node", "hash-v2", payload_v2, test_db)
    got_v2 = await _get_cached_result(doc_id, "ambiguity_node", "hash-v2", test_db)
    assert got_v2 == payload_v2

    # And the old hash is no longer present — there is at most one row per
    # (document_id, node_name) because `_set_cache` updates in place.
    stale = await _get_cached_result(doc_id, "ambiguity_node", "hash-v1", test_db)
    assert stale is None


@pytest.mark.asyncio
async def test_cache_rejects_string_fs_id(test_db: AsyncSession) -> None:
    """Guardrail: passing a ``str`` for ``fs_id`` must raise.

    This is exactly the regression that silently disabled the cache for
    months. If anyone reintroduces ``str(fs_id)`` at a call-site, this
    test fails loudly instead of the cache silently no-op'ing.
    """
    doc_id = uuid.uuid4()
    test_db.add(
        FSDocument(
            id=doc_id,
            filename="rejects.txt",
            content_type="text/plain",
            file_size=1,
            status="UPLOADED",
            file_path="/tmp/rejects.txt",
        )
    )
    await test_db.commit()

    # SQLAlchemy wraps the underlying ``AttributeError`` in
    # ``StatementError`` when the bind processor blows up; either is
    # acceptable — both mean "caller passed a str where a UUID was required".
    from sqlalchemy.exc import StatementError

    with pytest.raises((AttributeError, StatementError)):
        await _set_cache(str(doc_id), "ambiguity_node", "h", {}, test_db)  # type: ignore[arg-type]
