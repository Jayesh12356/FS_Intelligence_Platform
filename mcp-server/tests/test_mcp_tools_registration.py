"""Verify all MCP tools register correctly and the server module loads."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import mcp  # noqa: E402


@pytest.fixture(scope="module")
def tools():
    return asyncio.run(mcp.list_tools())


@pytest.fixture(scope="module")
def tool_names(tools):
    return {t.name for t in tools}


@pytest.fixture(scope="module")
def prompts():
    return asyncio.run(mcp.list_prompts())


@pytest.fixture(scope="module")
def prompt_names(prompts):
    return {p.name for p in prompts}


def test_mcp_server_loads():
    assert mcp is not None
    assert mcp.name == "fs-intelligence-platform"


def test_tool_count_at_least_85(tools):
    assert len(tools) >= 85, f"Expected >= 85 tools, got {len(tools)}"


def test_critical_analysis_tools_present(tool_names):
    expected = {
        "resolve_contradiction",
        "accept_contradiction_suggestion",
        "resolve_edge_case",
        "accept_edge_case_suggestion",
        "bulk_resolve_ambiguities",
        "bulk_resolve_contradictions",
        "bulk_accept_contradictions",
        "bulk_resolve_edge_cases",
        "bulk_accept_edge_cases",
        "get_analysis_progress",
        "cancel_analysis",
    }
    missing = expected - tool_names
    assert not missing, f"Missing analysis tools: {missing}"


def test_document_management_tools_present(tool_names):
    expected = {
        "delete_document",
        "reset_document_status",
        "edit_section",
        "add_section",
    }
    missing = expected - tool_names
    assert not missing, f"Missing document tools: {missing}"


def test_version_approval_tools_present(tool_names):
    expected = {
        "get_version_text",
        "revert_to_version",
        "reject_document",
        "get_approval_status",
    }
    missing = expected - tool_names
    assert not missing, f"Missing version/approval tools: {missing}"


def test_duplicate_library_tools_present(tool_names):
    expected = {
        "get_duplicates",
        "get_library_item",
        "get_suggestions",
    }
    missing = expected - tool_names
    assert not missing, f"Missing duplicate/library tools: {missing}"


def test_project_tools_present(tool_names):
    expected = {
        "list_projects",
        "create_project",
        "get_project",
        "assign_document_to_project",
    }
    missing = expected - tool_names
    assert not missing, f"Missing project tools: {missing}"


def test_idea_tools_present(tool_names):
    expected = {"generate_fs_from_idea", "generate_fs_guided"}
    missing = expected - tool_names
    assert not missing, f"Missing idea tools: {missing}"


def test_orchestration_tools_present(tool_names):
    expected = {
        "list_providers",
        "get_tool_config",
        "update_tool_config",
        "test_provider",
        "get_provider_capabilities",
    }
    missing = expected - tool_names
    assert not missing, f"Missing orchestration tools: {missing}"


def test_prompt_count_at_least_8(prompts):
    assert len(prompts) >= 8, f"Expected >= 8 prompts, got {len(prompts)}"


def test_new_prompts_present(prompt_names):
    expected = {"quick_analysis", "project_overview", "refine_and_analyze"}
    missing = expected - set(prompt_names)
    assert not missing, f"Missing prompts: {missing}"


def test_refine_and_analyze_prompt_present(prompt_names):
    assert "refine_and_analyze" in prompt_names, f"Missing refine_and_analyze prompt. Got: {prompt_names}"


def test_original_tools_still_present(tool_names):
    """Core tools from before the Phase 1 additions should still be registered."""
    core = {
        "list_documents", "get_document", "upload_document",
        "trigger_analysis", "get_ambiguities", "resolve_ambiguity",
        "get_contradictions", "get_edge_cases", "get_quality_score",
        "refine_fs", "run_quality_gate", "get_tasks",
        "get_dependency_graph", "register_file", "verify_task_completion",
        "export_to_jira", "get_pdf_report",
    }
    missing = core - tool_names
    assert not missing, f"Missing core tools: {missing}"
