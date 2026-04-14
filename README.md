# FS Intelligence Platform

AI-powered platform that transforms Functional Specification (FS) documents into developer-ready task breakdowns with ambiguity detection, adversarial validation, contradiction analysis, quality scoring, change impact tracking, autonomous build orchestration, and legacy code reverse documentation.

---

## What It Does

Upload a specification document. The platform runs an 12-node AI pipeline that detects ambiguities, contradictions, and edge-case gaps; scores quality; decomposes the spec into atomic developer tasks with effort estimates and acceptance criteria; maps every task back to its source section; generates test cases; and flags duplicate requirements across documents.

When the spec changes, upload a new version and get instant impact analysis showing which tasks break and how much rework is needed. For legacy systems with no documentation, upload a codebase ZIP and get a generated functional specification from the code.

An MCP (Model Context Protocol) server wraps the entire platform so AI coding agents (Cursor, Claude Code, Claude Desktop) can autonomously read analysis results, pick up tasks, resolve issues, and build products end-to-end.

---

## Core Capabilities

| Capability | Description |
|------------|-------------|
| **FS Ingestion** | Upload PDF, DOCX, or TXT specifications; parse into structured sections with vector embeddings |
| **Ambiguity Detection** | LLM-powered identification of vague, incomplete, or unclear requirements with severity classification |
| **Adversarial Validation** | CrewAI multi-agent debate (Red vs Blue vs Arbiter) reduces false-positive ambiguity flags |
| **Contradiction Analysis** | Pairwise section comparison for conflicting statements with resolution suggestions |
| **Edge Case Detection** | Identify missing scenarios, error handling gaps, and boundary conditions |
| **Quality Scoring** | Completeness, clarity, and consistency metrics with compliance tagging |
| **FS Refinement** | LLM-powered document improvement with before/after diff preview and version history |
| **Accept & Resolve Flow** | Accept AI suggestions to merge fixes into the document; bulk accept/resolve all issues at once |
| **Task Decomposition** | Break specs into atomic dev tasks with effort estimation, acceptance criteria, and tags |
| **Dependency Graph** | Task ordering with cycle detection and parallel-execution identification |
| **Traceability Matrix** | Link every task to its source FS section; highlight orphan tasks and uncovered sections |
| **Change Impact Analysis** | Upload FS versions, diff sections, classify task impact, estimate rework days |
| **Legacy Code Reverse FS** | Upload codebases (ZIP), auto-generate functional specifications from source code |
| **Semantic Duplicate Detection** | Qdrant-powered similarity search across documents |
| **Requirement Library** | Reusable requirements with semantic search, auto-populated on approval |
| **Collaboration** | Section-level comments, @-mentions, approval workflows, full audit trail |
| **JIRA Export** | Push tasks as epics + stories to JIRA (simulated mode for demo) |
| **Confluence Export** | Publish full analysis reports as Confluence pages |
| **PDF/DOCX Reports** | Download styled intelligence reports |
| **Test Case Generation** | LLM-powered test cases from acceptance criteria with CSV export |
| **Build Engine** | Autonomous build state tracking, file registry, pre/post-build gates, snapshots with rollback |
| **MCP Server** | Full platform exposed as native tools for AI coding agents |
| **Monitoring Dashboard** | Real-time MCP session tracking, activity log, build progress |

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | FastAPI, Python 3.11+ | Async API layer, 16 routers, 90+ endpoints |
| Pipeline | LangGraph | Stateful 12-node analysis pipeline + impact + reverse + refinement pipelines |
| LLM Interface | Direct SDKs (Anthropic, OpenAI-compat) | Multi-provider model abstraction |
| Adversarial Agents | CrewAI | Multi-agent debate on ambiguities |
| Semantic Search | Qdrant | Duplicate detection, requirement library, embeddings |
| Relational Store | PostgreSQL | 25+ tables: versions, audit trail, traceability, tasks, build state |
| Frontend | Next.js 14, TypeScript, Tailwind CSS | 20+ page App Router UI with Framer Motion |
| Embeddings | OpenAI / Groq / OpenRouter | Configurable embedding provider |
| Reports | reportlab, python-docx | PDF and Word export |
| MCP Server | Python MCP SDK | 20+ tools for AI coding agents |
| Deployment | Docker Compose | 4-service containerization |

### Supported LLM Providers

| Provider | Example Model | Env Variable |
|----------|--------------|--------------|
| Anthropic | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-4o-mini` | `OPENAI_API_KEY` |
| Groq | `llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| OpenRouter | `anthropic/claude-sonnet-4-20250514` | `OPENROUTER_API_KEY` |

OpenRouter supports role-based model routing: separate models for reasoning, build, long-context, and fallback tasks.

---

## Quick Start

### 1. Clone and Configure

```bash
git clone <repo-url>
cd fs_intelligence_platform
cp .env.example .env
```

Edit `.env` with your API keys. At minimum:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
PRIMARY_MODEL=gpt-4o-mini
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
```

### 2. Start Infrastructure

```bash
docker compose up -d postgres qdrant
```

PostgreSQL on port 5434, Qdrant on port 6336.

### 3. Install and Run Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 4. Install and Run Frontend

```bash
cd frontend
npm install
npm run dev
```

### 5. Open

Navigate to `http://localhost:3001`:

1. Upload an FS document (PDF, DOCX, or TXT).
2. Click **Parse** to extract sections, then **Analyze** to run the full pipeline.
3. Explore ambiguities, quality scores, tasks, traceability, and more.
4. Refine the FS with AI suggestions, accept resolutions, bulk-resolve issues.
5. Export to JIRA, Confluence, or download PDF/DOCX reports.

### Full Docker (All Services)

```bash
docker compose up -d
```

Backend: `http://localhost:8000` | Frontend: `http://localhost:3001`

---

## Analysis Pipeline

The core analysis runs a 12-node LangGraph pipeline:

```text
parse -> ambiguity -> debate -> contradiction -> edge_case -> quality ->
task_decomposition -> dependency -> traceability -> duplicate -> testcase -> END
```

| Node | What It Does |
|------|-------------|
| **parse** | Validate and pass through parsed sections |
| **ambiguity** | Detect vague/incomplete requirements (severity: LOW/MEDIUM/HIGH) |
| **debate** | CrewAI adversarial debate on HIGH flags (Red vs Blue vs Arbiter) |
| **contradiction** | Find contradictory statements between section pairs |
| **edge_case** | Identify missing error handling, edge cases, gaps |
| **quality** | Score completeness/clarity/consistency, tag compliance areas |
| **task_decomposition** | Break sections into atomic dev tasks with effort + criteria |
| **dependency** | Build task graph, detect cycles, find parallel opportunities |
| **traceability** | Link every task to its source section |
| **duplicate** | Semantic search for duplicates across documents |
| **testcase** | Generate test cases from acceptance criteria |

Additional pipelines: **Impact** (version_node -> impact_node -> rework_node), **Reverse FS** (reverse_fs_node -> reverse_quality_node), **Refinement** (issues_collector -> suggestion -> rewriter -> validation).

---

## Project Structure

```text
fs_intelligence_platform/
├── README.md                      # This file
├── CONTEXT.md                     # AI-consumable system reference
├── docker-compose.yml             # Postgres + Qdrant + Backend + Frontend
├── .env.example                   # Full configuration reference
│
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI entrypoint with 16 routers
│   │   ├── config.py              # Centralized settings (50+ variables)
│   │   ├── api/                   # 16 routers, 90+ endpoints
│   │   ├── pipeline/
│   │   │   ├── graph.py           # LangGraph analysis + impact + reverse graphs
│   │   │   ├── refinement_graph.py # FS refinement pipeline
│   │   │   ├── state.py           # Shared pipeline state
│   │   │   └── nodes/             # 16 pipeline node modules
│   │   ├── agents/                # CrewAI debate (Red/Blue/Arbiter)
│   │   ├── integrations/          # JIRA + Confluence clients
│   │   ├── llm/                   # Multi-provider LLM client
│   │   ├── parsers/               # PDF/DOCX/TXT + code parsers
│   │   ├── vector/                # Qdrant store + embeddings
│   │   ├── db/                    # SQLAlchemy models (25+ tables)
│   │   └── models/                # Pydantic schemas (80+ models)
│   ├── tests/                     # Pytest test suite
│   ├── scripts/                   # Utility scripts (reset_all.py)
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── app/                   # 20+ Next.js App Router pages
│   │   ├── components/            # 15 shared UI components
│   │   └── lib/api.ts             # TypeScript API client (80+ functions)
│   ├── package.json
│   └── Dockerfile
│
├── mcp-server/
│   ├── server.py                  # MCP server entrypoint
│   ├── tools/                     # 20+ MCP tool modules
│   ├── resources/                 # MCP resource providers
│   ├── prompts/                   # Autonomous build loop prompt
│   └── README.md                  # MCP setup guide
│
├── docs/
│   └── MANUAL.md                  # Full technical and user manual
│
└── roadmap/
    └── CONTEXT_L1..L10.md         # Per-level implementation history
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | High-level overview, quick start, architecture summary |
| `CONTEXT.md` | Complete AI-consumable system reference for Cursor/Claude/Copilot |
| `docs/MANUAL.md` | Full technical manual: pipeline details, API reference, configuration, operational notes |
| `roadmap/CONTEXT_L1..L10.md` | Per-level implementation history and design decisions |
| `mcp-server/README.md` | MCP server setup and tool documentation |
| `.env.example` | Complete configuration reference with comments |

---

## Configuration

| Area | Key Variables |
|------|--------------|
| **LLM** | `LLM_PROVIDER` (anthropic / openai / groq / openrouter) |
| **Models** | `PRIMARY_MODEL`, `REASONING_MODEL`, `BUILD_MODEL`, `LONGCONTEXT_MODEL`, `FALLBACK_MODEL` |
| **Embeddings** | `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL` |
| **Database** | `DATABASE_URL`, `QDRANT_URL` |
| **JIRA** | `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` |
| **Confluence** | `CONFLUENCE_URL`, `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN`, `CONFLUENCE_SPACE_KEY` |
| **MCP Guards** | `MCP_MONITORING_ENABLED`, `MCP_MIN_QUALITY_SCORE`, `MCP_REQUIRE_TRACEABILITY` |
| **Reverse FS** | `REVERSE_LARGE_UPLOAD_ENABLED`, `REVERSE_MAX_ARCHIVE_SIZE_MB`, and 10+ tuning knobs |

LLM and embedding providers are independent. See `.env.example` for the complete reference.

---

## Research Contribution

> *"DSPy-optimised ambiguity detection with adversarial multi-agent validation outperforms single-LLM approaches on enterprise FS documents -- measured against human-labelled ground truth."*

- **Baseline**: Single GPT-4 call with manual prompt
- **Proposed**: DSPy-optimised pipeline + CrewAI adversarial debate
- **Metric**: Precision/recall of ambiguity flags vs human-annotated FS document set
- **Benchmark**: `backend/app/pipeline/benchmarks/debate_benchmark.py`

---

## License

This project is an academic/internal reference implementation for MTech thesis evaluation.
Add your chosen license before public or commercial deployment.
