# FS Intelligence Platform -- System Context

> This file is the authoritative AI-consumable reference for the entire system.
> Any AI tool (Cursor, Claude, Copilot) should read this file first to understand
> what exists, how it works, and where to find things.

---

## 1. What This System Is

An AI-powered platform that transforms Functional Specification (FS) documents into developer-ready work. It ingests specs (PDF/DOCX/TXT), runs a multi-node LLM analysis pipeline, decomposes requirements into tasks, tracks changes, generates test cases, and orchestrates autonomous builds via MCP.

**Status**: All 10 implementation levels complete. Production-ready for local deployment.

---

## 2. Architecture Overview

```text
                       ┌─────────────────┐
                       │   Next.js 14     │  Port 3001
                       │   Frontend       │  20+ pages, 15 components
                       └────────┬────────┘
                                │ REST API calls
                       ┌────────▼────────┐
                       │   FastAPI        │  Port 8000
                       │   Backend        │  16 routers, 90+ endpoints
                       └──┬──────┬───┬───┘
                          │      │   │
              ┌───────────┘      │   └───────────┐
              ▼                  ▼               ▼
     ┌────────────┐    ┌──────────────┐  ┌───────────┐
     │ PostgreSQL  │    │   Qdrant     │  │ LLM APIs  │
     │ 25+ tables  │    │ Vector DB    │  │ Multi-    │
     │ Port 5434   │    │ Port 6336    │  │ provider  │
     └────────────┘    └──────────────┘  └───────────┘

     ┌────────────────────────────────────────────┐
     │  MCP Server (Python)                       │
     │  20+ tools wrapping the FastAPI backend    │
     │  Used by Cursor / Claude Code / Desktop    │
     └────────────────────────────────────────────┘
```

---

## 3. Tech Stack

| Layer | Technology | Details |
|-------|-----------|---------|
| Backend | FastAPI + Python 3.11+ | Fully async, SQLAlchemy 2.0, Pydantic V2 |
| Pipeline | LangGraph | Analysis (12 nodes), Impact (3 nodes), Reverse (2 nodes), Refinement (4 stages) |
| LLM | Anthropic / OpenAI / Groq / OpenRouter | Via `app/llm/client.py`, role-based model routing for OpenRouter |
| Adversarial Agents | CrewAI | Red/Blue/Arbiter debate on HIGH ambiguity flags |
| Vector DB | Qdrant | Collections: `fs_requirements` (embeddings), `fs_library` (reusable reqs) |
| Relational DB | PostgreSQL | 25+ tables via SQLAlchemy async ORM |
| Frontend | Next.js 14, TypeScript, Tailwind, Framer Motion | App Router, 20+ pages |
| Embeddings | OpenAI text-embedding-3-small (1536d) | Configurable provider |
| Reports | reportlab (PDF), python-docx (DOCX) | Styled exports with text fallback |
| MCP Server | Python MCP SDK | 20+ tools, resources, autonomous build prompt |
| Deploy | Docker Compose | 4 services: postgres, qdrant, backend, frontend |

---

## 4. Database Models (25+ tables)

| Model | Purpose |
|-------|---------|
| `FSProject` | Project container for grouping documents |
| `FSDocument` | Core document entity (status: UPLOADED -> PARSED -> ANALYZING -> COMPLETE) |
| `FSVersion` | Immutable version snapshots of document text |
| `AnalysisResult` | Raw JSON analysis output per document |
| `AmbiguityFlagDB` | Ambiguity flags with severity, reason, clarification question, resolved status |
| `ContradictionDB` | Section-pair contradictions with suggested_resolution, resolved status |
| `EdgeCaseGapDB` | Missing scenarios with suggested_addition, resolved status |
| `ComplianceTagDB` | Compliance area tags (PAYMENTS, AUTH, PII, EXTERNAL_API, etc.) |
| `FSTaskDB` | Decomposed developer tasks with effort, acceptance criteria, deps, tags, status |
| `TraceabilityEntryDB` | Task-to-section mapping for traceability matrix |
| `DebateResultDB` | Adversarial debate transcripts (Red/Blue/Arbiter arguments + verdict) |
| `FSChangeDB` | Section-level changes between versions |
| `TaskImpactDB` | Task impact classification per version change |
| `ReworkEstimateDB` | Rework cost rollup per version |
| `CodeUploadDB` | Uploaded codebases for reverse FS generation |
| `DuplicateFlagDB` | Cross-document duplicate requirement matches |
| `FSCommentDB` | Section-level collaboration comments |
| `FSMentionDB` | @-mention tracking in comments |
| `FSApprovalDB` | Approval workflow records |
| `AuditEventDB` | Full audit trail (11 event types) |
| `TestCaseDB` | Generated test cases with preconditions, steps, expected results |
| `MCPSessionDB` | MCP build session tracking |
| `MCPSessionEventDB` | Per-event telemetry within MCP sessions |
| `BuildStateDB` | Autonomous build progress (phase, task index, status) |
| `FileRegistryDB` | Files created during build mapped to tasks/sections |
| `BuildSnapshotDB` | Rollback snapshots of build state |
| `PipelineCacheDB` | Cached pipeline node results to skip LLM on re-runs |

---

## 5. API Routers (16 routers, 90+ endpoints)

### fs_router (`/api/fs`)
- `POST /upload` -- Upload FS document
- `GET /` -- List documents
- `GET /{id}` -- Document detail with sections
- `GET /{id}/status` -- Lightweight status check
- `DELETE /{id}` -- Soft-delete document
- `POST /{id}/reset-status` -- Reset stuck processing
- `POST /{id}/parse` -- Parse into sections + embed
- `PATCH /{id}/sections/{idx}` -- Edit section heading/content
- `POST /{id}/sections` -- Add new section

### analysis_router (`/api/fs`)
- `GET /{id}/analysis-progress` -- Real-time pipeline progress
- `POST /{id}/analyze` -- Run full 12-node pipeline
- `POST /{id}/cancel-analysis` -- Cancel in-flight analysis
- `POST /{id}/refine` -- Run refinement pipeline (auto/targeted/full modes)
- `POST /{id}/refine/accept` -- Persist refined text as new version
- `GET /{id}/ambiguities` -- List ambiguity flags
- `PATCH /{id}/ambiguities/{fid}` -- Resolve ambiguity
- `POST /{id}/ambiguities/bulk-resolve` -- Bulk resolve all ambiguities
- `GET /{id}/quality-score/refresh` -- Recompute quality from DB
- `GET /{id}/contradictions` -- List contradictions
- `PATCH /{id}/contradictions/{cid}` -- Resolve contradiction
- `POST /{id}/contradictions/{cid}/accept` -- Accept resolution (merge into text)
- `POST /{id}/contradictions/bulk-accept` -- Bulk accept all contradiction resolutions
- `POST /{id}/contradictions/bulk-resolve` -- Bulk resolve all contradictions
- `GET /{id}/edge-cases` -- List edge case gaps
- `PATCH /{id}/edge-cases/{eid}` -- Resolve edge case
- `POST /{id}/edge-cases/{eid}/accept` -- Accept suggestion (merge into text)
- `POST /{id}/edge-cases/bulk-accept` -- Bulk accept all edge case suggestions
- `POST /{id}/edge-cases/bulk-resolve` -- Bulk resolve all edge cases
- `GET /{id}/quality-score` -- Quality dashboard (scores + issues + compliance)
- `GET /{id}/debate-results` -- Adversarial debate outcomes

### tasks_router (`/api/fs`)
- `GET /{id}/tasks` -- List decomposed tasks
- `GET /{id}/tasks/{tid}` -- Single task detail
- `PATCH /{id}/tasks/{tid}` -- Update task (status, etc.)
- `GET /{id}/tasks/dependency-graph` -- Task dependency graph
- `GET /{id}/traceability` -- Traceability matrix

### impact_router (`/api/fs`)
- `POST /{id}/version` -- Upload new FS version with diff + impact analysis
- `GET /{id}/versions` -- List versions
- `GET /{id}/versions/{vid}/text` -- Version body text
- `POST /{id}/versions/{vid}/revert` -- Revert to version
- `GET /{id}/versions/{vid}/diff` -- Section-level diff
- `GET /{id}/impact/{vid}` -- Full impact analysis
- `GET /{id}/impact/{vid}/rework` -- Rework estimate

### build_router (`/api/fs`)
- `POST /{id}/build-state` -- Create/reset build state
- `GET /{id}/build-state` -- Current build progress
- `PATCH /{id}/build-state` -- Update build progress
- `POST /{id}/file-registry` -- Register created file
- `GET /{id}/file-registry` -- List files (filter by task/section)
- `GET /{id}/tasks/{tid}/context` -- Aggregated build context for a task
- `GET /{id}/tasks/{tid}/verify` -- Heuristic verification of task completion
- `POST /{id}/place-requirement` -- Find best section for new requirement
- `GET /{id}/pre-build-check` -- Pre-build quality gate
- `GET /{id}/post-build-check` -- Post-build coverage check
- `POST /{id}/snapshots` -- Save rollback snapshot
- `POST /{id}/snapshots/{sid}/rollback` -- Restore from snapshot
- `GET /{id}/pipeline-cache` -- Cached node results
- `DELETE /{id}/pipeline-cache` -- Clear cache
- `GET /{id}/build-prompt` -- Generate structured build prompt

### mcp_router (`/api/mcp`)
- `POST /sessions` -- Create MCP session
- `GET /sessions` -- List sessions
- `GET /sessions/{sid}` -- Get session
- `POST /sessions/{sid}/events` -- Append event
- `GET /sessions/{sid}/events` -- List events
- `GET /sessions/{sid}/events/stream` -- SSE event stream

### collab_router (`/api/fs`)
- `POST /{id}/sections/{idx}/comments` -- Add comment with @-mentions
- `GET /{id}/comments` -- List comments
- `PATCH /{id}/comments/{cid}/resolve` -- Resolve comment

### export_router (`/api/fs`)
- `POST /{id}/export/jira` -- Export to JIRA (epic + stories)
- `POST /{id}/export/confluence` -- Publish to Confluence
- `GET /{id}/test-cases` -- List test cases
- `GET /{id}/test-cases/csv` -- CSV download
- `GET /{id}/export/pdf` -- PDF metadata
- `GET /{id}/export/pdf/download` -- PDF download
- `GET /{id}/export/docx` -- DOCX metadata
- `GET /{id}/export/docx/download` -- DOCX download

### Other routers
- `approval_router` -- Submit/approve/reject workflow + history
- `audit_router` -- Per-document audit event log
- `activity_router` -- Global activity timeline with filters
- `code_router` -- Upload ZIP, generate FS from code, quality report
- `duplicate_router` -- Cross-document duplicate flags
- `library_router` -- Semantic library search + suggestions
- `project_router` -- Project CRUD + document assignment
- `health_router` -- DB/Qdrant/LLM composite health check

---

## 6. Analysis Pipeline (LangGraph)

### Main Analysis (12 nodes, sequential)
```
START -> parse_node -> ambiguity_node -> debate_node -> contradiction_node ->
edge_case_node -> quality_node -> task_decomposition_node -> dependency_node ->
traceability_node -> duplicate_node -> testcase_node -> END
```

### Impact Pipeline (3 nodes)
```
START -> version_node -> impact_node -> rework_node -> END
```

### Reverse FS Pipeline (2 nodes)
```
START -> reverse_fs_node -> reverse_quality_node -> END
```

### Refinement Pipeline (4 stages, sequential function calls)
```
issues_collector_node -> suggestion_node -> rewriter_node -> validation_node
```

**Pipeline caching**: When `db` is passed, each node checks `PipelineCacheDB` for a matching `input_hash` and skips the LLM call on cache hit.

**Progress tracking**: In-memory `_analysis_progress` dict provides real-time node status for the frontend stepper.

---

## 7. Frontend Pages (20+ routes)

| Route | Purpose |
|-------|---------|
| `/` | Dashboard with KPIs, recent documents, feature cards |
| `/upload` | Drag-and-drop file upload with project assignment |
| `/documents` | Document list with search, status badges, delete |
| `/documents/[id]` | Document detail: sections (editable), analysis summary, pipeline actions |
| `/documents/[id]/ambiguities` | Ambiguity flags with severity filter tabs, debate transcripts, resolve/bulk-resolve |
| `/documents/[id]/quality` | Quality gauge + sub-scores, contradictions tab (accept/resolve/bulk), edge cases tab (accept/resolve/bulk), compliance tab |
| `/documents/[id]/refine` | AI refinement with before/after diff, accept/reject, version history with revert |
| `/documents/[id]/tasks` | Task board with dependency graph and traceability tabs |
| `/documents/[id]/impact` | Version upload, timeline, diff viewer, task impact, rework estimate |
| `/documents/[id]/traceability` | Section-task coverage matrix with orphan warnings |
| `/documents/[id]/collab` | Comments, approval workflow, audit timeline |
| `/analysis` | Redirects to `/documents` |
| `/monitoring` | Activity log + MCP build session tracker with auto-refresh |
| `/reverse` | Code upload, FS generation, quality report, section viewer |
| `/library` | Semantic search across requirement library |
| `/projects` | Project CRUD with document count KPIs |
| `/projects/[id]` | Editable project detail, document upload, status grid |

### Shared Components (15)
`PageShell`, `Badge`/`StatusBadge`, `KpiCard`, `AnimatedNumber`, `ScoreBar`, `QualityGauge`, `Tabs`, `EmptyState`, `SearchInput`, `Modal`, `CopyButton`, `AnalysisProgress`, `LoadingSkeleton`, `MotionWrap` (PageMotion/StaggerList/FadeIn)

---

## 8. MCP Server (20+ tools)

Located in `mcp-server/`. Wraps the FastAPI backend for AI coding agents.

**Tool categories**: documents, analysis, tasks, impact, build, collaboration, exports, reverse

**Key tools**: `get_document`, `get_sections`, `run_analysis`, `get_ambiguities`, `resolve_ambiguity`, `get_tasks`, `get_build_prompt`, `autonomous_build_from_fs`, `start_build_loop`, `register_file`, `pre_build_check`, `post_build_check`, `create_snapshot`, `rollback_to_snapshot`, `refine_fs`, `check_library_for_reuse`

**Resources**: `fs_document` (full document context), `task_board` (task list)

**Autonomous build prompt**: 7-phase protocol (pre-flight, audit, clear blockers, build plan, build, checkpoint, verify, export)

---

## 9. Quality Score System

Quality is computed from **unresolved** issues:

| Sub-score | Formula |
|-----------|---------|
| **Completeness** | % of sections without unresolved edge-case gaps |
| **Clarity** | % of sections without unresolved ambiguity flags |
| **Consistency** | 1 - (contradiction_rate) based on section pair combinations |
| **Overall** | Weighted average (completeness 40%, clarity 35%, consistency 25%) |

All scores clamped to [0, 100]. Compliance tags are informational and do not affect scores.

**Accept flow**: Accepting a suggestion (edge case or contradiction) merges the AI-generated text into the document at the relevant section, creates a new version, marks the issue resolved, and the quality score updates live.

**Bulk actions**: Accept All / Resolve All buttons process all unresolved items in a single API call.

---

## 10. Key Conventions

- All pipeline nodes are async
- All LLM calls go through `backend/app/llm/client.py` only
- All API responses follow `{ data, error, meta }` envelope via `APIResponse[T]`
- All external calls wrapped in try/except with graceful fallback
- Type hints on every function
- Python logging only (no print statements)
- No hardcoded strings (settings or constants)
- Frontend uses `PageShell` wrapper for all pages
- Frontend uses `useCallback` + `useEffect` for data fetching
- `visibilitychange` listener on detail page for cross-page sync

---

## 11. Project Structure

```text
fs_intelligence_platform/
├── README.md                      # High-level overview
├── CONTEXT.md                     # THIS FILE -- AI system reference
├── docker-compose.yml             # 4-service container setup
├── .env.example                   # Full config reference
│
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app with 16 routers
│   │   ├── config.py              # Settings (50+ env vars)
│   │   ├── api/                   # 16 route modules
│   │   │   ├── fs_router.py       # Document CRUD + parse
│   │   │   ├── analysis_router.py # Analysis + refine + accept/resolve/bulk
│   │   │   ├── tasks_router.py    # Tasks + deps + traceability
│   │   │   ├── impact_router.py   # Versions + diff + impact + rework
│   │   │   ├── build_router.py    # Build state + registry + gates + cache
│   │   │   ├── mcp_router.py      # MCP sessions + events
│   │   │   ├── collab_router.py   # Comments + mentions
│   │   │   ├── export_router.py   # JIRA/Confluence/PDF/DOCX/CSV
│   │   │   ├── approval_router.py # Approval workflow
│   │   │   ├── audit_router.py    # Audit event log
│   │   │   ├── activity_router.py # Global activity feed
│   │   │   ├── code_router.py     # Code upload + reverse FS
│   │   │   ├── duplicate_router.py # Duplicate flags
│   │   │   ├── library_router.py  # Requirement library search
│   │   │   ├── project_router.py  # Project CRUD
│   │   │   └── health_router.py   # Health check
│   │   ├── pipeline/
│   │   │   ├── graph.py           # LangGraph builders (analysis/impact/reverse)
│   │   │   ├── refinement_graph.py # Refinement pipeline
│   │   │   ├── state.py           # FSAnalysisState TypedDict
│   │   │   ├── benchmarks/        # Debate accuracy benchmark
│   │   │   └── nodes/             # 16 node modules
│   │   ├── agents/                # CrewAI: red_agent, blue_agent, arbiter_agent, debate_crew
│   │   ├── integrations/          # jira.py, confluence.py
│   │   ├── llm/client.py          # Multi-provider LLM (Anthropic/OpenAI/Groq/OpenRouter)
│   │   ├── parsers/               # pdf, docx, txt, code, chunker, section_extractor
│   │   ├── vector/                # Qdrant client + fs_store (embed/search)
│   │   ├── db/                    # models.py (25+ ORM models), base.py, init_db.py
│   │   └── models/schemas.py      # 80+ Pydantic schemas
│   ├── tests/                     # Pytest suite (15 test files)
│   ├── scripts/reset_all.py       # DB + Qdrant full reset
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── app/                   # 20+ page routes
│   │   ├── components/            # 15 shared components
│   │   └── lib/api.ts             # 80+ API functions + 60+ TypeScript interfaces
│   ├── package.json
│   └── Dockerfile
│
├── mcp-server/
│   ├── server.py                  # MCP entrypoint
│   ├── config.py                  # MCP config
│   ├── tools/                     # 8 tool modules (documents, analysis, tasks, build, etc.)
│   ├── resources/                 # fs_document, task_board
│   ├── prompts/agent_loop.py      # Autonomous build protocol
│   └── README.md
│
├── docs/MANUAL.md                 # Full technical manual
└── roadmap/CONTEXT_L1..L10.md     # Implementation history
```

---

## 12. Implementation History (Levels 1-10)

| Level | Name | What Was Built |
|-------|------|---------------|
| **L1** | Foundation | Project skeleton, Docker Compose, FastAPI backend, file upload CRUD, LLM client, Qdrant client, Next.js frontend shell, health check |
| **L2** | Document Parsing | PDF/DOCX/TXT parsers, section-aware chunker, OpenAI embeddings + Qdrant storage, parse endpoint, frontend sections accordion |
| **L3** | Ambiguity Detection | LangGraph pipeline (2 nodes), LLM ambiguity flags with severity, AmbiguityFlagDB, analysis API, multi-provider LLM, frontend ambiguity review page |
| **L4** | Deep Analysis | Pipeline extended to 5 nodes, contradiction detection, edge case gaps, quality scorer, compliance tags, 3 new DB tables, quality dashboard UI |
| **L5** | Task Decomposition | Pipeline to 8 nodes, LLM task breakdown with effort/criteria/tags, dependency graph with cycle detection, traceability matrix, task board UI |
| **L6** | Adversarial Validation | Pipeline to 9 nodes, CrewAI debate (Red/Blue/Arbiter) on HIGH flags, DebateResultDB, debate transcript UI, benchmark script |
| **L7** | Change Impact | Impact pipeline (3 nodes), difflib section diff, LLM task impact classification, rework estimator, version upload, impact dashboard UI |
| **L8** | Legacy Code Reverse | Reverse pipeline (2 nodes), code parser (Python AST + regex JS/TS/Java/Go), 4-step LLM FS generation, quality scoring, reverse dashboard UI |
| **L9** | Semantic Intelligence | Qdrant duplicate detection, requirement library, comments + @-mentions, approval workflow, full audit trail, 5 new DB tables, library search UI |
| **L10** | Integrations + Polish | JIRA/Confluence export, test case generation, PDF/DOCX reports, CSV export, monitoring dashboard, traceability matrix UI, build engine with MCP tools |

### Post-L10 Enhancements
- **FS Refinement Pipeline**: LLM-powered document improvement with before/after diff, targeted and full rewrite modes, version history with revert
- **Accept/Resolve Flow**: Accept AI suggestions to merge fixes into document text for edge cases and contradictions; bulk accept/resolve for all issue types
- **Cross-Page Sync**: Unresolved counts on detail page, visibilitychange refetch, live quality score updates after every mutation
- **Build Engine**: 4 new DB tables, 15 build-related endpoints, 14 MCP tools, 7-phase autonomous build protocol
- **MCP Server**: Complete tool suite for AI coding agents with resources and autonomous build prompt

---

## 13. Adding New Features

When extending the platform, follow this pattern:

1. **Backend**: Add DB model in `models.py`, schema in `schemas.py`, pipeline node in `nodes/`, router endpoint in `api/`
2. **Frontend**: Add API function in `api.ts`, page in `app/`, use `PageShell` wrapper and shared components
3. **MCP**: Add tool wrapper in `mcp-server/tools/`, register in `server.py`
4. **Documentation**: Update this `CONTEXT.md` section 12 with a new entry, update `docs/MANUAL.md`, add `roadmap/CONTEXT_L{N}.md` if needed
5. **Tests**: Add test file in `backend/tests/`

---

## 14. Configuration Reference

See `.env.example` for the complete list. Key groups:

**Database**: `DATABASE_URL`, `DATABASE_URL_SYNC`, `QDRANT_URL`, `QDRANT_API_KEY`

**LLM**: `LLM_PROVIDER` (anthropic/openai/groq/openrouter), `PRIMARY_MODEL`, `REASONING_MODEL`, `BUILD_MODEL`, `LONGCONTEXT_MODEL`, `FALLBACK_MODEL`

**Embeddings**: `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`

**App**: `ENVIRONMENT`, `UPLOAD_DIR`, `MAX_UPLOAD_SIZE_MB`, `CORS_ALLOW_ORIGINS`

**Integrations**: `JIRA_URL/EMAIL/API_TOKEN/PROJECT_KEY`, `CONFLUENCE_URL/EMAIL/API_TOKEN/SPACE_KEY`

**MCP Guards**: `MCP_MONITORING_ENABLED`, `MCP_REQUIRE_ZERO_HIGH_AMBIGUITIES`, `MCP_MIN_QUALITY_SCORE`, `MCP_REQUIRE_TRACEABILITY`, `MCP_DRY_RUN_DEFAULT`

**Reverse FS**: `REVERSE_LARGE_UPLOAD_ENABLED`, `REVERSE_MAX_ARCHIVE_SIZE_MB`, `REVERSE_MAX_UNCOMPRESSED_MB`, `REVERSE_MAX_ARCHIVE_FILES`, `REVERSE_INCLUDE_EXTENSIONS`, and 8 more tuning knobs
