=============================================================
BUILD: MCP SERVER FOR FS INTELLIGENCE PLATFORM
=============================================================
Read the full manual at /MANUAL.md and /CONTEXT.md /roadmap before 
writing a single line of code.

Goal: Build a production-grade MCP (Model Context Protocol) 
server that wraps the FS Intelligence Platform's FastAPI backend 
and exposes it as native tools to AI coding agents (Cursor, 
Claude Code, Claude Desktop). The MCP server allows any 
connected AI agent to autonomously read FS analysis results, 
pick up dev tasks, resolve ambiguities, check traceability, 
and self-correct until the codebase reaches full spec compliance.

=============================================================
WHAT TO BUILD WITHOUT AFFECTING EXISTING PRODUCT/CODE
=============================================================

Create: /mcp-server/
├── server.py              ← MCP server entrypoint (FastMCP)
├── tools/
│   ├── documents.py       ← document management tools
│   ├── analysis.py        ← ambiguity/contradiction/quality tools
│   ├── tasks.py           ← task + dependency + traceability tools
│   ├── impact.py          ← version diff + rework estimate tools
│   ├── collaboration.py   ← comments + approval + audit tools
│   ├── exports.py         ← jira/confluence/pdf/docx tools
│   └── reverse.py         ← legacy code reverse FS tools
├── resources/
│   ├── fs_document.py     ← expose FS docs as MCP resources
│   └── task_board.py      ← expose task board as MCP resource
├── prompts/
│   └── agent_loop.py      ← built-in agentic loop prompt template
├── config.py              ← reads same .env as backend
├── requirements.txt
└── README.md

=============================================================
TECH STACK
=============================================================
Use: fastmcp (pip install fastmcp)
  — FastMCP is the fastest way to build MCP servers in Python
  — It handles tool registration, schema generation, transport
  — Supports stdio (Cursor/Claude Code) and SSE (web clients)

The MCP server is a THIN WRAPPER over the existing FastAPI 
backend. It does NOT duplicate any business logic. Every tool 
makes an HTTP call to http://localhost:8000/api/... and returns 
the result. If the backend is down, tools return a clear error.

=============================================================
STEP 1 — SERVER ENTRYPOINT
=============================================================
Create /mcp-server/server.py:

```python
from fastmcp import FastMCP
from tools import documents, analysis, tasks, impact, 
                  collaboration, exports, reverse

mcp = FastMCP(
    name="fs-intelligence-platform",
    instructions="""
    You are connected to the FS Intelligence Platform.
    
    AUTONOMOUS AGENT LOOP — follow this order every session:
    
    1. DISCOVER: Call list_documents to see all FS documents.
    2. SELECT: Pick the document with status COMPLETE or highest priority.
    3. AUDIT: Call get_quality_score, get_ambiguities, get_contradictions,
       get_edge_cases in parallel. Build a mental model of all issues.
    4. PLAN: Call get_tasks and get_dependency_graph. Identify which tasks 
       map to unresolved ambiguities (cross-reference via traceability).
    5. EXECUTE: For each HIGH severity ambiguity:
       - Read the debate_results to see if CrewAI has already reasoned on it
       - If verdict is AMBIGUOUS: resolve it with a concrete proposal
       - Call resolve_ambiguity with your proposed resolution
    6. BUILD: Work through tasks in topological order (respect dependencies).
       For each task: implement the code, then call mark_task_complete.
    7. VERIFY: After each task, call get_traceability to confirm the task 
       is linked to a section. If orphaned, fix it.
    8. LOOP: Repeat from step 3 after every batch of changes.
       Stop only when get_quality_score returns >= 90 AND 
       all ambiguities are resolved AND all tasks are complete.
    
    You have full read + write access to the platform.
    Never skip the audit step. Never implement before planning.
    """
)

# Register all tool modules
documents.register(mcp)
analysis.register(mcp)
tasks.register(mcp)
impact.register(mcp)
collaboration.register(mcp)
exports.register(mcp)
reverse.register(mcp)

if __name__ == "__main__":
    mcp.run()  # stdio by default — works with Cursor + Claude Code
```

=============================================================
STEP 2 — IMPLEMENT ALL TOOLS
=============================================================
Each tool file follows this pattern:

```python
# tools/analysis.py
import httpx
from fastmcp import FastMCP
from config import BACKEND_URL

def register(mcp: FastMCP):

    @mcp.tool()
    async def get_ambiguities(document_id: str) -> dict:
        """
        Returns all ambiguity flags for a document.
        Each flag has: id, description, severity (HIGH/MEDIUM/LOW),
        section, status (OPEN/RESOLVED), and debate verdict if available.
        Use this to understand what is unclear in the spec before building.
        """
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BACKEND_URL}/api/fs/{document_id}/ambiguities"
            )
            return r.json()

    @mcp.tool()
    async def resolve_ambiguity(
        document_id: str, 
        flag_id: str, 
        resolution: str
    ) -> dict:
        """
        Resolves an ambiguity flag with a concrete resolution statement.
        Call this after reasoning about the flag using debate_results.
        resolution: a clear, implementable statement that removes ambiguity.
        """
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{BACKEND_URL}/api/fs/{document_id}/ambiguities/{flag_id}",
                json={"resolution": resolution, "status": "RESOLVED"}
            )
            return r.json()

    @mcp.tool()
    async def get_contradictions(document_id: str) -> dict:
        """
        Returns contradictory statement pairs found in the spec.
        Each entry shows section_a vs section_b and the conflict description.
        Always resolve contradictions before starting task implementation.
        """
        ...

    @mcp.tool()
    async def get_quality_score(document_id: str) -> dict:
        """
        Returns overall quality score (0-100) and sub-scores:
        completeness, clarity, consistency.
        Target: overall >= 90 before marking work complete.
        """
        ...

    @mcp.tool()
    async def get_debate_results(document_id: str) -> dict:
        """
        Returns CrewAI adversarial debate transcripts for HIGH severity flags.
        RedAgent argues it IS ambiguous. BlueAgent argues it is clear.
        ArbiterAgent issues final verdict: CLEAR (false positive) or AMBIGUOUS.
        Read these before resolving any HIGH severity flag.
        """
        ...

    @mcp.tool()
    async def get_edge_cases(document_id: str) -> dict:
        """
        Returns gaps in error handling, edge cases, and missing scenarios.
        Use this to ensure implementation covers all edge paths, not just 
        the happy path.
        """
        ...
```

Implement ALL tools listed below. Every tool must have:
- A clear docstring explaining WHEN and WHY an agent uses it
- Proper type hints
- httpx async calls to the backend
- Error handling: if backend returns non-200, return 
  { "error": str, "status_code": int }

COMPLETE TOOL LIST — implement every one:

documents.py:
  - list_documents() → all docs with status
  - get_document(document_id) → detail + sections
  - upload_document(file_path) → upload from local path
  - trigger_analysis(document_id) → start 11-node pipeline
  - get_document_status(document_id) → PENDING/ANALYZING/COMPLETE
  - get_sections(document_id) → parsed sections list

analysis.py:
  - get_ambiguities(document_id)
  - resolve_ambiguity(document_id, flag_id, resolution)
  - get_contradictions(document_id)
  - get_edge_cases(document_id)
  - get_quality_score(document_id)
  - get_compliance_tags(document_id)
  - get_debate_results(document_id)

tasks.py:
  - get_tasks(document_id) → all tasks with effort/tags/criteria
  - get_task(document_id, task_id) → single task detail
  - update_task(document_id, task_id, updates) → mark complete etc
  - get_dependency_graph(document_id) → nodes + edges (DAG)
  - get_traceability(document_id) → section → task mappings
  - get_test_cases(document_id) → generated test cases

impact.py:
  - upload_version(document_id, file_path) → new FS version
  - list_versions(document_id)
  - get_version_diff(document_id, v1_id, v2_id)
  - get_impact_analysis(document_id, version_id)
  - get_rework_estimate(document_id, version_id)

collaboration.py:
  - get_comments(document_id)
  - add_comment(document_id, section_id, content)
  - resolve_comment(document_id, comment_id)
  - submit_for_approval(document_id)
  - approve_document(document_id, approval_id)
  - get_audit_trail(document_id)

exports.py:
  - export_to_jira(document_id)
  - export_to_confluence(document_id)
  - get_pdf_report(document_id) → download URL
  - get_docx_report(document_id) → download URL
  - export_test_cases_csv(document_id)

reverse.py:
  - upload_codebase(zip_path) → code_upload_id
  - generate_reverse_fs(code_upload_id)
  - get_generated_fs(code_upload_id) → sections
  - get_reverse_quality_report(code_upload_id)
  - list_code_uploads()

=============================================================
STEP 3 — MCP RESOURCES (read-only data the agent can browse)
=============================================================
Create /mcp-server/resources/fs_document.py:

```python
def register(mcp: FastMCP):

    @mcp.resource("fs://documents")
    async def all_documents() -> str:
        """Browse all FS documents in the platform"""
        ...

    @mcp.resource("fs://documents/{document_id}/tasks")
    async def document_tasks(document_id: str) -> str:
        """Full task board for a document as formatted markdown"""
        ...

    @mcp.resource("fs://documents/{document_id}/analysis-summary")
    async def analysis_summary(document_id: str) -> str:
        """
        Full analysis summary as markdown:
        quality score, ambiguity count by severity,
        contradiction count, top 5 tasks by effort.
        The agent should read this resource at session start.
        """
        ...
```

=============================================================
STEP 4 — AGENTIC LOOP PROMPT
=============================================================
Create /mcp-server/prompts/agent_loop.py:

```python
def register(mcp: FastMCP):

    @mcp.prompt()
    async def start_build_loop(document_id: str) -> str:
        """
        Activates the autonomous build loop for a specific document.
        Returns a structured prompt that guides the agent through
        the full analyse → plan → build → verify → loop cycle.
        """
        return f"""
        # Autonomous Build Session — Document {document_id}
        
        You are an autonomous software engineer connected to the 
        FS Intelligence Platform. Your mission is to reach absolute 
        perfection on document {document_id}.
        
        ## Definition of Done
        - Quality score >= 90
        - Zero OPEN HIGH severity ambiguities
        - Zero OPEN contradictions  
        - All tasks marked COMPLETE
        - Full traceability coverage (no orphaned tasks)
        - All test cases passing
        
        ## Execution Protocol
        
        ### Phase 1 — Audit (always first)
        Call in parallel:
        - get_quality_score("{document_id}")
        - get_ambiguities("{document_id}")
        - get_contradictions("{document_id}")
        - get_edge_cases("{document_id}")
        - get_debate_results("{document_id}")
        
        Report: current score, issue counts by severity, 
        biggest risk areas.
        
        ### Phase 2 — Triage
        Call get_tasks("{document_id}") and get_dependency_graph("{document_id}")
        Cross-reference tasks with HIGH ambiguity flags via traceability.
        Build a priority queue: tasks blocked by ambiguity come LAST.
        
        ### Phase 3 — Resolve Ambiguities
        For each HIGH ambiguity (sorted by section order):
        1. Read debate_results for this flag
        2. If AMBIGUOUS verdict: propose a concrete resolution
        3. Call resolve_ambiguity with your proposal
        4. Log: "Resolved: [flag description] → [your resolution]"
        
        ### Phase 4 — Build Tasks (topological order)
        For each unblocked task (no pending dependencies):
        1. Read task detail including acceptance_criteria
        2. Implement the code change
        3. Call update_task to mark IN_PROGRESS then COMPLETE
        4. Verify traceability link exists
        
        ### Phase 5 — Verify
        After every 5 tasks:
        - Re-run get_quality_score
        - Re-run get_ambiguities (check nothing regressed)
        - Check get_traceability for orphans
        
        ### Phase 6 — Loop
        If Definition of Done is NOT met: return to Phase 1.
        If Definition of Done IS met:
        - Call export_to_jira("{document_id}")
        - Call get_pdf_report("{document_id}")
        - Report: "Build complete. Quality: [score]/100. 
          Tasks completed: N. Ambiguities resolved: N."
        
        Begin Phase 1 now.
        """

    @mcp.prompt()
    async def fix_single_ambiguity(
        document_id: str, 
        flag_id: str
    ) -> str:
        """Focused prompt to resolve one specific ambiguity flag"""
        ...

    @mcp.prompt()  
    async def implement_task(
        document_id: str, 
        task_id: str
    ) -> str:
        """Focused prompt to implement one specific task"""
        ...
```

=============================================================
STEP 5 — CONFIG
=============================================================
Create /mcp-server/config.py:

```python
import os
from dotenv import load_dotenv

load_dotenv("../.env")  # reads the same .env as the backend

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
```

=============================================================
STEP 6 — CURSOR + CLAUDE CODE CONFIGURATION FILES
=============================================================
Create these config files so agents connect with zero manual setup:

### /mcp-server/.cursor/mcp.json
```json
{
  "mcpServers": {
    "fs-intelligence-platform": {
      "command": "python",
      "args": ["/absolute/path/to/mcp-server/server.py"],
      "env": {
        "BACKEND_URL": "http://localhost:8000"
      }
    }
  }
}
```

### /mcp-server/claude_desktop_config.json
```json
{
  "mcpServers": {
    "fs-intelligence-platform": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/absolute/path/to/mcp-server",
      "env": {
        "BACKEND_URL": "http://localhost:8000"
      }
    }
  }
}
```

### /mcp-server/claude_code_config.json  
(for `claude mcp add` command)
```json
{
  "name": "fs-intelligence-platform",
  "command": "python server.py",
  "description": "FS Intelligence Platform — full analysis, tasks, exports"
}
```

Also create /mcp-server/README.md with:
1. Installation: pip install fastmcp httpx python-dotenv
2. Start backend first: uvicorn app.main:app --port 8000
3. Test MCP: python server.py (should print tool list)
4. Add to Cursor: copy .cursor/mcp.json to project root
5. Add to Claude Desktop: merge claude_desktop_config.json 
   into ~/Library/Application Support/Claude/claude_desktop_config.json
6. Add to Claude Code: claude mcp add fs-intelligence-platform 
   "python /path/to/server.py"
7. Trigger build loop: use prompt "start_build_loop" with document_id

=============================================================
STEP 7 — REQUIREMENTS
=============================================================
Create /mcp-server/requirements.txt:
fastmcp>=2.0.0
httpx>=0.27.0
python-dotenv>=1.0.0

=============================================================
STEP 8 — VERIFY IT WORKS
=============================================================
After building:

1. Start the backend:
   cd backend && uvicorn app.main:app --port 8000 --reload

2. Test MCP server launches:
   cd mcp-server && python server.py
   Expected output: lists all registered tools with their schemas

3. Test with MCP Inspector:
   npx @modelcontextprotocol/inspector python server.py
   Verify every tool appears with correct input schema

4. Test one tool manually via inspector:
   Call list_documents() → should return documents from your backend

5. Test in Cursor:
   - Copy .cursor/mcp.json to your project root
   - Open Cursor settings → MCP → verify fs-intelligence-platform appears
   - Open Cursor chat, type: 
     "Use the fs-intelligence-platform MCP to list all documents 
      and show me a quality summary of the latest one"
   - Cursor should call list_documents and get_quality_score live

6. Test the build loop:
   In Cursor chat:
   "Use the start_build_loop prompt for document [your_doc_id] 
    and begin autonomous improvement"
   
   Watch Cursor autonomously:
   - Audit the FS
   - Resolve ambiguities
   - Pick up tasks in dependency order  
   - Loop until quality >= 90

=============================================================
CONSTRAINTS
=============================================================
- The MCP server is stateless — no database, no cache
- All state lives in the FS Platform backend (PostgreSQL + Qdrant)
- Every tool call must complete in < 30 seconds
- Tools must never crash the server — wrap everything in try/except
- Tool docstrings are the agent's only instructions — make them precise
- No tool does more than one thing (single responsibility)
- All tools return dicts (JSON-serialisable)