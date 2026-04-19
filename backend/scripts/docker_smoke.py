"""Tiny end-to-end smoke against the dockerized stack.

Posts a small spec to /api/fs/upload and asserts a complete Pydantic
APIResponse envelope. Designed to be run from the host against the
docker-compose'd backend on http://localhost:8000.
"""

from __future__ import annotations

import json
import time

import httpx

BASE = "http://localhost:8000"
SPEC = b"""# Tiny TODO API

REQ-1: The system shall expose a POST /todos endpoint that creates a todo.
REQ-2: The system shall return the created todo's id within 200ms.
REQ-3: The system shall persist todos across process restarts.
"""


def main() -> int:
    t0 = time.monotonic()
    with httpx.Client(base_url=BASE, timeout=20.0, follow_redirects=True) as c:
        h = c.get("/health").json()
        assert h["data"]["status"] == "healthy", h
        print(
            f"  /health OK: db={h['data']['db']['status']} qdrant={h['data']['qdrant']['status']} llm={h['data']['llm']['status']}"
        )

        up = c.post(
            "/api/fs/upload",
            files={"file": ("smoke.txt", SPEC, "text/plain")},
        )
        assert up.status_code == 200, (up.status_code, up.text[:300])
        env = up.json()
        assert env["error"] is None, env
        doc_id = env["data"]["id"]
        print(f"  /api/fs/upload OK: doc_id={doc_id}")

        got = c.get(f"/api/fs/{doc_id}")
        assert got.status_code == 200, got.text[:300]
        meta = got.json()["data"]
        assert meta["filename"] == "smoke.txt"
        print(f"  /api/fs/{{id}} OK: filename={meta['filename']} size={meta.get('file_size')}")

        listing = c.get("/api/fs", params={"limit": 5})
        assert listing.status_code == 200
        items = listing.json()["data"]
        assert any(d["id"] == doc_id for d in items.get("documents", items if isinstance(items, list) else []))
        print("  /api/fs (list) OK: uploaded doc visible")

    print(json.dumps({"status": "pass", "elapsed_s": round(time.monotonic() - t0, 2)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
