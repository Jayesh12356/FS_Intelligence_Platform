"""Shared HTTP helpers for MCP tools."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from config import BACKEND_URL, MCP_TIMEOUT_SECONDS


def _error_payload(message: str, status_code: int) -> dict[str, Any]:
    return {"error": message, "status_code": status_code}


def _session_id() -> Optional[str]:
    sid = os.getenv("MCP_SESSION_ID", "").strip()
    return sid or None


async def emit_session_event(
    event_type: str,
    *,
    phase: int = 0,
    status: str = "ok",
    message: str = "",
    payload: Optional[dict[str, Any]] = None,
) -> None:
    """Best-effort MCP event emission; never raises."""
    sid = _session_id()
    if not sid:
        return
    try:
        async with httpx.AsyncClient(timeout=MCP_TIMEOUT_SECONDS) as client:
            await client.post(
                f"{BACKEND_URL}/api/mcp/sessions/{sid}/events",
                json={
                    "event_type": event_type,
                    "phase": phase,
                    "status": status,
                    "message": message,
                    "payload": payload or {},
                },
            )
    except Exception:
        # Event logging should never block primary tool execution.
        return


async def request_json(
    method: str,
    path: str,
    *,
    json: Optional[dict[str, Any]] = None,
    files: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Send a request to backend and always return JSON-serializable dict."""
    url = f"{BACKEND_URL}{path}"
    try:
        await emit_session_event(
            "tool_request",
            message=f"{method} {path}",
            payload={"path": path, "method": method},
        )
        async with httpx.AsyncClient(timeout=MCP_TIMEOUT_SECONDS) as client:
            response = await client.request(method, url, json=json, files=files, params=params)
        if response.status_code >= 400:
            try:
                err = response.json()
            except Exception:
                err = {"detail": response.text}
            payload = _error_payload(str(err), response.status_code)
            await emit_session_event(
                "tool_response_error",
                status="error",
                message=f"{method} {path} -> {response.status_code}",
                payload=payload,
            )
            return payload
        try:
            payload = response.json()
            await emit_session_event(
                "tool_response_ok",
                message=f"{method} {path} -> {response.status_code}",
                payload={"status_code": response.status_code},
            )
            return payload
        except Exception:
            return {"data": {"text": response.text}}
    except httpx.RequestError as exc:
        payload = _error_payload(f"Backend request failed: {exc}", 503)
        await emit_session_event("tool_response_error", status="error", message=str(exc), payload=payload)
        return payload
    except Exception as exc:
        payload = _error_payload(f"Unexpected MCP wrapper error: {exc}", 500)
        await emit_session_event("tool_response_error", status="error", message=str(exc), payload=payload)
        return payload

