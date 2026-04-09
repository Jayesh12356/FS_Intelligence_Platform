"""Tests for MCP monitoring APIs."""

import pytest


class TestMCPMonitoringAPI:
    @pytest.mark.asyncio
    async def test_create_session_and_append_event(self, client):
        create = await client.post(
            "/api/mcp/sessions",
            json={
                "target_stack": "Next.js + FastAPI",
                "source": "test-suite",
                "dry_run": True,
                "total_phases": 2,
            },
        )
        assert create.status_code == 200
        session_id = create.json()["data"]["id"]

        append = await client.post(
            f"/api/mcp/sessions/{session_id}/events",
            json={
                "event_type": "manifest_generated",
                "phase": 1,
                "status": "ok",
                "message": "Manifest ready",
                "payload": {"tasks": 5},
            },
        )
        assert append.status_code == 200
        assert append.json()["data"]["event_type"] == "manifest_generated"

        events = await client.get(f"/api/mcp/sessions/{session_id}/events")
        assert events.status_code == 200
        assert events.json()["data"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_sessions(self, client):
        res = await client.get("/api/mcp/sessions")
        assert res.status_code == 200
        assert "sessions" in res.json()["data"]

