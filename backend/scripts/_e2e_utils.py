"""Shared helpers for the E2E driver scripts.

Everything here is HTTP-only against the already-running backend. No direct
DB access, no Python-side imports of the backend app.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

BACKEND_URL = os.environ.get("E2E_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
FRONTEND_URL = os.environ.get("E2E_FRONTEND_URL", "http://127.0.0.1:3001").rstrip("/")
RUNTIME_PATH = Path(__file__).resolve().parent / ".e2e_runtime.json"
REPORT_DIR = Path(__file__).resolve().parent.parent.parent / "reports"

logger = logging.getLogger("e2e")


# ── Logging ────────────────────────────────────────────────────────────


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )


# ── Runtime state (survives resumes) ───────────────────────────────────


@dataclass
class ProjectState:
    provider: str
    name: str
    project_id: str | None = None
    document_id: str | None = None
    filename: str | None = None
    quality_score: float | None = None
    high_ambiguities: int | None = None
    task_count: int | None = None
    section_count: int | None = None
    build_state_status: str | None = None
    build_zip_path: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class ReverseRun:
    provider: str
    document_id: str | None = None
    section_count: int | None = None
    flow_count: int | None = None
    quality_score: float | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class Runtime:
    started_at: float = field(default_factory=time.time)
    projects: dict[str, ProjectState] = field(default_factory=dict)
    reverses: dict[str, ReverseRun] = field(default_factory=dict)
    code_upload_id: str | None = None
    phase_status: dict[str, str] = field(default_factory=dict)
    repairs: list[dict] = field(default_factory=list)
    endpoint_hits: dict[str, int] = field(default_factory=dict)
    mcp_session_id: str | None = None

    def save(self) -> None:
        def _encode(obj: Any) -> Any:
            if hasattr(obj, "__dict__"):
                return asdict(obj) if hasattr(obj, "__dataclass_fields__") else obj.__dict__
            raise TypeError(str(type(obj)))

        payload = {
            "started_at": self.started_at,
            "projects": {k: asdict(v) for k, v in self.projects.items()},
            "reverses": {k: asdict(v) for k, v in self.reverses.items()},
            "code_upload_id": self.code_upload_id,
            "phase_status": self.phase_status,
            "repairs": self.repairs,
            "endpoint_hits": self.endpoint_hits,
            "mcp_session_id": self.mcp_session_id,
        }
        RUNTIME_PATH.write_text(json.dumps(payload, indent=2, default=_encode))

    @classmethod
    def load(cls) -> Runtime:
        if not RUNTIME_PATH.exists():
            return cls()
        try:
            raw = json.loads(RUNTIME_PATH.read_text())
        except Exception:
            return cls()
        rt = cls(
            started_at=raw.get("started_at", time.time()),
            code_upload_id=raw.get("code_upload_id"),
            phase_status=raw.get("phase_status", {}),
            repairs=raw.get("repairs", []),
            endpoint_hits=raw.get("endpoint_hits", {}),
            mcp_session_id=raw.get("mcp_session_id"),
        )
        for k, v in (raw.get("projects") or {}).items():
            rt.projects[k] = ProjectState(**v)
        for k, v in (raw.get("reverses") or {}).items():
            rt.reverses[k] = ReverseRun(**v)
        return rt


# ── HTTP client ────────────────────────────────────────────────────────

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=10.0)
# Long timeout for analyze / refine / reverse-FS where CLI providers (claude_code)
# can comfortably take 15-25 minutes on 8+ LLM nodes.
LONG_TIMEOUT = httpx.Timeout(connect=10.0, read=2700.0, write=60.0, pool=10.0)


class BackendClient:
    """Thin httpx wrapper with endpoint-hit accounting and nice errors."""

    def __init__(self, runtime: Runtime, base_url: str = BACKEND_URL) -> None:
        self.runtime = runtime
        self._client = httpx.AsyncClient(base_url=base_url, timeout=DEFAULT_TIMEOUT)

    async def __aenter__(self) -> BackendClient:
        return self

    async def __aexit__(self, *a: Any) -> None:
        await self._client.aclose()

    def _bump(self, method: str, path: str) -> None:
        key = f"{method} {path}"
        self.runtime.endpoint_hits[key] = self.runtime.endpoint_hits.get(key, 0) + 1

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        self._bump(method.upper(), path)
        r = await self._client.request(method, path, **kwargs)
        return r

    async def jget(self, path: str, **kwargs: Any) -> Any:
        r = await self.request("GET", path, **kwargs)
        r.raise_for_status()
        return r.json()

    async def jpost(self, path: str, **kwargs: Any) -> Any:
        r = await self.request("POST", path, **kwargs)
        r.raise_for_status()
        return r.json()

    async def jput(self, path: str, **kwargs: Any) -> Any:
        r = await self.request("PUT", path, **kwargs)
        r.raise_for_status()
        return r.json()

    async def jpatch(self, path: str, **kwargs: Any) -> Any:
        r = await self.request("PATCH", path, **kwargs)
        r.raise_for_status()
        return r.json()

    async def jdelete(self, path: str, **kwargs: Any) -> Any:
        r = await self.request("DELETE", path, **kwargs)
        r.raise_for_status()
        return r.json()


# ── Provider switching ─────────────────────────────────────────────────


async def switch_provider(client: BackendClient, provider: str) -> dict:
    """Flip llm_provider + build_provider + frontend_provider to `provider`.

    Returns the resulting config dict.
    """
    body = {
        "llm_provider": provider,
        "build_provider": provider if provider in ("claude_code", "cursor", "api") else "api",
        "frontend_provider": provider,
        "fallback_chain": ["api"],
    }
    data = await client.jput("/api/orchestration/config", json=body)
    cfg = data["data"]
    logger.info(
        "Provider switched -> llm=%s build=%s frontend=%s",
        cfg["llm_provider"],
        cfg["build_provider"],
        cfg["frontend_provider"],
    )
    return cfg


# ── Step decorator / repair loop ───────────────────────────────────────


@contextmanager
def step(name: str, runtime: Runtime):
    logger.info("--- %s", name)
    t0 = time.time()
    try:
        yield
        runtime.phase_status[name] = "ok"
        logger.info("    %s OK (%.1fs)", name, time.time() - t0)
    except Exception as exc:
        runtime.phase_status[name] = f"fail: {type(exc).__name__}: {exc}"
        logger.error("    %s FAIL: %s", name, exc)
        raise
    finally:
        runtime.save()


async def repair_loop(
    name: str,
    fn: Callable[[], Any],
    runtime: Runtime,
    max_attempts: int = 5,
    backoff: float = 3.0,
) -> Any:
    """Run `fn` up to max_attempts times, logging each failure to runtime.repairs."""
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            runtime.repairs.append(
                {
                    "step": name,
                    "attempt": attempt,
                    "error": f"{type(exc).__name__}: {exc}",
                    "ts": time.time(),
                }
            )
            runtime.save()
            if attempt >= max_attempts:
                break
            sleep_for = backoff * attempt
            logger.warning(
                "    [repair] %s attempt %d/%d failed: %s — retrying in %.1fs",
                name,
                attempt,
                max_attempts,
                exc,
                sleep_for,
            )
            await asyncio.sleep(sleep_for)
    assert last_exc is not None
    raise last_exc


# ── Small utilities ────────────────────────────────────────────────────


async def run_analysis_with_progress(
    client: BackendClient,
    doc_id: str,
    poll_interval: float = 25.0,
) -> dict:
    """Kick off POST /analyze with a long timeout; log progress snapshots.

    Handles claude_code / cursor providers where the synchronous analyze
    endpoint may take 15-25 minutes on Windows CLI subprocess roundtrips.
    If the HTTP call times out, falls back to polling the document status
    until COMPLETE / ERROR.
    """
    analyze_task = asyncio.create_task(client.request("POST", f"/api/fs/{doc_id}/analyze", timeout=LONG_TIMEOUT))

    async def _progress() -> None:
        while not analyze_task.done():
            try:
                prog = await client.jget(f"/api/fs/{doc_id}/analysis-progress")
                p = prog.get("data", {}) if isinstance(prog, dict) else {}
                current = p.get("current_node") or "-"
                done = len(p.get("completed_nodes") or [])
                total = p.get("total_nodes") or 0
                status = p.get("status") or "?"
                logger.info("  analyze progress: status=%s node=%s (%d/%d)", status, current, done, total)
            except Exception as exc:  # noqa: BLE001
                logger.debug("progress poll error: %s", exc)
            try:
                await asyncio.wait_for(asyncio.shield(analyze_task), timeout=poll_interval)
            except TimeoutError:
                pass
            except Exception:  # noqa: BLE001
                return

    progress_task = asyncio.create_task(_progress())
    try:
        r = await analyze_task
    except (httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
        logger.warning("  analyze HTTP timed out (%s) — polling for completion", exc)
        return await _poll_until_terminal(client, doc_id)
    finally:
        progress_task.cancel()
        try:
            await progress_task
        except Exception:  # noqa: BLE001
            pass
    if r.status_code >= 400:
        # Fall through to polling — backend may still finish
        logger.warning("  analyze returned HTTP %s — polling", r.status_code)
        return await _poll_until_terminal(client, doc_id)
    return r.json().get("data", {})


async def _poll_until_terminal(client: BackendClient, doc_id: str, timeout_s: float = 1800.0) -> dict:
    t0 = time.time()
    last_log = 0.0
    while time.time() - t0 < timeout_s:
        try:
            prog = await client.jget(f"/api/fs/{doc_id}/analysis-progress")
            p = prog.get("data", {})
            status = (p.get("status") or "").upper()
            if status in ("COMPLETE", "ERROR"):
                logger.info("  poll terminal status=%s", status)
                return p
            if time.time() - last_log > 25:
                logger.info("  poll status=%s node=%s", status, p.get("current_node"))
                last_log = time.time()
        except Exception as exc:  # noqa: BLE001
            logger.debug("poll error: %s", exc)
        await asyncio.sleep(10)
    raise TimeoutError(f"analysis did not reach terminal status within {timeout_s}s")


async def wait_for_quality(
    client: BackendClient,
    doc_id: str,
    min_score: float,
    max_refine: int = 3,
) -> dict:
    """Fetch quality-score, run refinement loop if below threshold."""
    for i in range(max_refine + 1):
        data = await client.jget(f"/api/fs/{doc_id}/quality-score")
        score = float(data["data"]["quality_score"]["overall"])
        logger.info("  quality attempt %d: %.1f", i, score)
        if score >= min_score:
            return data["data"]
        if i == max_refine:
            return data["data"]
        logger.info("  below threshold %s — running refinement...", min_score)
        try:
            await client.jpost(f"/api/fs/{doc_id}/refine")
        except httpx.HTTPStatusError as exc:
            logger.warning("  refine call failed: %s", exc)
            break
    return data["data"]


def banner(text: str) -> str:
    line = "=" * max(60, len(text) + 4)
    return f"\n{line}\n  {text}\n{line}"


__all__ = [
    "BackendClient",
    "BACKEND_URL",
    "FRONTEND_URL",
    "Runtime",
    "ProjectState",
    "ReverseRun",
    "REPORT_DIR",
    "banner",
    "logger",
    "repair_loop",
    "run_analysis_with_progress",
    "setup_logging",
    "step",
    "switch_provider",
    "wait_for_quality",
    "LONG_TIMEOUT",
]
