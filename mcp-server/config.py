"""Configuration for MCP server."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
MCP_TIMEOUT_SECONDS = float(os.getenv("MCP_TIMEOUT_SECONDS", "25"))

# MCP autonomous guardrails (local-first, configurable)
MCP_REQUIRE_ZERO_HIGH_AMBIGUITIES = os.getenv("MCP_REQUIRE_ZERO_HIGH_AMBIGUITIES", "true").lower() == "true"
MCP_MIN_QUALITY_SCORE = float(os.getenv("MCP_MIN_QUALITY_SCORE", "90"))
MCP_REQUIRE_TRACEABILITY = os.getenv("MCP_REQUIRE_TRACEABILITY", "true").lower() == "true"
MCP_DRY_RUN_DEFAULT = os.getenv("MCP_DRY_RUN_DEFAULT", "false").lower() == "true"

