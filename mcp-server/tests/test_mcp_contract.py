"""Contract tests for MCP tools.

Covers two concerns:

1. Schema presence — every registered MCP tool must expose a non-empty name,
   a description, and a valid JSON-schema-ish parameters dict.

2. Error shape — when the backend returns 4xx/5xx or is unreachable, the
   shared ``request_json`` helper must return a predictable ``{"error": ...,
   "status_code": int}`` envelope instead of raising. Every tool that calls
   ``request_json`` therefore gets the same error envelope.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import mcp  # noqa: E402
from tools._http import request_json  # noqa: E402


@pytest.fixture(scope="module")
def tools():
    return asyncio.run(mcp.list_tools())


def test_every_tool_has_name(tools) -> None:
    for tool in tools:
        assert tool.name, f"Tool {tool!r} missing a name"
        assert isinstance(tool.name, str)


def test_every_tool_has_description(tools) -> None:
    missing: list[str] = []
    for tool in tools:
        description = (tool.description or "").strip()
        if not description:
            missing.append(tool.name)
    assert not missing, f"Tools missing description: {missing}"


def test_every_tool_has_valid_parameters_schema(tools) -> None:
    bad: list[str] = []
    for tool in tools:
        params = tool.parameters
        if not isinstance(params, dict):
            bad.append(f"{tool.name}: not a dict")
            continue
        if params.get("type") != "object":
            bad.append(f"{tool.name}: type != object")
            continue
        if "properties" not in params:
            bad.append(f"{tool.name}: missing 'properties'")
    assert not bad, f"Tools with malformed parameter schemas: {bad}"


def test_tool_names_are_unique(tools) -> None:
    names = [t.name for t in tools]
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates, f"Duplicate tool names: {duplicates}"


def _mock_http_response(status_code: int, json_body: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = ValueError("not json")
    resp.text = text or (str(json_body) if json_body else "")
    return resp


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 409, 422])
async def test_request_json_returns_error_envelope_on_4xx(status_code: int) -> None:
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.request = AsyncMock(
        return_value=_mock_http_response(status_code, {"detail": "boom"})
    )

    with patch("tools._http.httpx.AsyncClient", return_value=mock_client):
        result = await request_json("GET", "/api/anything")

    assert isinstance(result, dict)
    assert "error" in result
    assert result["status_code"] == status_code


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
async def test_request_json_returns_error_envelope_on_5xx(status_code: int) -> None:
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.request = AsyncMock(
        return_value=_mock_http_response(status_code, {"detail": "server error"})
    )

    with patch("tools._http.httpx.AsyncClient", return_value=mock_client):
        result = await request_json("GET", "/api/anything")

    assert result["status_code"] == status_code
    assert "error" in result


@pytest.mark.asyncio
async def test_request_json_handles_network_error() -> None:
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.request = AsyncMock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with patch("tools._http.httpx.AsyncClient", return_value=mock_client):
        result = await request_json("POST", "/api/anything", json={"a": 1})

    assert result["status_code"] == 503
    assert "Backend request failed" in result["error"]


@pytest.mark.asyncio
async def test_request_json_handles_non_json_success_body() -> None:
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.request = AsyncMock(
        return_value=_mock_http_response(200, None, text="plaintext body"),
    )

    with patch("tools._http.httpx.AsyncClient", return_value=mock_client):
        result = await request_json("GET", "/api/plain")

    assert result == {"data": {"text": "plaintext body"}}


@pytest.mark.asyncio
async def test_request_json_preserves_json_on_success() -> None:
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.request = AsyncMock(
        return_value=_mock_http_response(200, {"data": {"items": [1, 2, 3]}}),
    )

    with patch("tools._http.httpx.AsyncClient", return_value=mock_client):
        result = await request_json("GET", "/api/anything")

    assert result == {"data": {"items": [1, 2, 3]}}


_REPRESENTATIVE_TOOLS = [
    # (tool_name, kwargs used to invoke the underlying Python function)
    ("list_documents", {}),
    ("get_document", {"document_id": "abc"}),
    ("get_ambiguities", {"document_id": "abc"}),
    ("list_projects", {}),
    ("get_project", {"project_id": "abc"}),
    ("list_providers", {}),
    ("get_tool_config", {}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("error_status", [404, 500])
@pytest.mark.parametrize("tool_name,kwargs", _REPRESENTATIVE_TOOLS)
async def test_representative_tools_propagate_error_envelope(
    tools, tool_name: str, kwargs: dict, error_status: int,
) -> None:
    """Every MCP tool that talks to the backend should surface the shared
    ``{error, status_code}`` envelope when the backend fails."""

    async def stub_request(method: str, path: str, **_kw):
        return {"error": f"boom@{path}", "status_code": error_status}

    tool = next((t for t in tools if t.name == tool_name), None)
    assert tool is not None, f"Tool {tool_name!r} not registered"

    # Each tool module imports request_json at module scope, so patch it
    # on every candidate module to guarantee the stub is hit.
    for module_path in (
        "tools.documents", "tools.analysis", "tools.projects",
        "tools.orchestration", "tools.tasks", "tools.exports",
        "tools.impact", "tools.duplicates", "tools.approval",
        "tools.reverse", "tools.idea", "tools.collaboration",
        "tools.build",
    ):
        patch(f"{module_path}.request_json", new=stub_request).start()
    try:
        result = await tool.fn(**kwargs)
    finally:
        patch.stopall()

    assert isinstance(result, dict)
    assert result.get("status_code") == error_status
    assert "error" in result
