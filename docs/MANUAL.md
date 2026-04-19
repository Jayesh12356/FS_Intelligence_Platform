# FS Intelligence Platform -- Technical and User Manual

This manual covers the complete system as implemented through Level 10 plus all
post-L10 enhancements (refinement, accept/resolve flow, build engine, MCP server).

For a concise architectural overview with mermaid diagrams, see
[ARCHITECTURE.md](./ARCHITECTURE.md). For subscription-tool guides, see
[GUIDE_CURSOR.md](./GUIDE_CURSOR.md), [GUIDE_CLAUDE_CODE.md](./GUIDE_CLAUDE_CODE.md),
and [GUIDE_WEB_UI.md](./GUIDE_WEB_UI.md).

---

## 1. System Overview

The FS Intelligence Platform transforms Functional Specification documents into
developer-ready work through AI-powered analysis:

1. **Upload** -- Ingest FS documents (PDF, DOCX, TXT) or legacy codebases (ZIP).
2. **Parse** -- Extract structured sections, generate vector embeddings, store in Qdrant.
3. **Analyze** -- Run a 11-node LangGraph pipeline that detects ambiguities, contradictions,
   edge cases, quality issues, and duplicates; decomposes into tasks; generates test cases.
4. **Validate** -- Adversarial multi-agent debate (CrewAI) challenges HIGH-severity ambiguity
   flags to reduce false positives.
5. **Refine** -- AI-powered document improvement with before/after diff preview.
6. **Accept/Resolve** -- Merge AI suggestions into the document text; bulk operations available.
7. **Track** -- Traceability matrix, version history, change impact analysis, rework estimation.
8. **Export** -- JIRA, Confluence, PDF, DOCX, CSV exports.
9. **Build** -- Autonomous build orchestration via MCP tools with pre/post-build gates.

### Pick your providers (two roles, three providers)

The platform asks two questions in **Settings**:

1. **Document LLM** — who runs Generate FS, Analyze, Refine,
   Reverse FS and Impact? Pick **Direct API** (server-side OpenRouter
   / Anthropic keys), **Claude Code** (local `claude` CLI), or
   **Cursor** (paste-per-action handoff — every click in the UI
   opens a modal with a one-shot mega-prompt that you paste into a
   fresh Cursor Agent chat; MCP tools submit the result back).
2. **Build Agent** — who drives the Build step? Pick **Cursor**
   (paste the build prompt from `/documents/{id}/build` into a
   Cursor Agent chat) or **Claude Code** (headless `claude -p`,
   dispatched with one click from the Build page's *Run Build Now*
   button). **Direct API** is intentionally unsupported for Build.

`api` and `claude_code` are synchronous and drive the usual LLM
pipeline. `cursor` is asynchronous and paste-driven — the backend
mints a `CursorTaskDB` row, returns `{mode: "cursor_task", task_id,
prompt, mcp_snippet}`, and the frontend opens a `CursorTaskModal`
that polls until `status = done`.

Token-economy guarantee: the bridge never falls back to Direct API.
`orchestrated_call_llm` consults the provider registry exactly once;
on failure it raises `LLMError`. The previously-exposed flags
`ORCHESTRATION_ENABLED`, `ORCHESTRATION_STRICT_LLM`,
`CURSOR_LLM_REQUEST_TIMEOUT_SEC`, `CURSOR_WORKER_TTL_SEC`,
`CURSOR_WORKER_PRESENCE_WAIT_SEC`, and `CURSOR_QUEUE_CLAIM_BATCH`
have been removed. Remaining environment variables:
`CLAUDE_CODE_CLI_PATH`, `LLM_TIMEOUT_S`, `LLM_RETRY_ATTEMPTS`,
`BACKEND_SELF_URL`, `CURSOR_TASK_TTL_SEC` (see root `.env.example`).

---

## 2. End-to-End Data Flow

### Document Ingestion
1. `POST /api/fs/upload` receives the file.
2. `FSDocument` row created with status `UPLOADED`.
3. `POST /api/fs/{id}/parse` triggers parsing:
   - Parser selected by file type (PDF via PyPDF2, DOCX via python-docx, TXT direct).
   - Section extractor splits content into heading + content blocks.
   - Dense embeddings generated via configurable provider.
   - Chunks + vectors upserted into Qdrant `fs_requirements` collection.
   - Status transitions to `PARSED`.

### Analysis Pipeline
1. `POST /api/fs/{id}/analyze` triggers the full pipeline.
2. Status transitions: `PARSED -> ANALYZING -> COMPLETE` (or `ERROR`).
3. 12 nodes execute sequentially; each reads/writes shared `FSAnalysisState`.
4. Results persisted to PostgreSQL: ambiguities, contradictions, edge cases, compliance tags,
   tasks, dependencies, traceability entries, debate results, test cases, duplicate flags.
5. Frontend polls `GET /api/fs/{id}/analysis-progress` every 3 seconds for real-time stepper.

### Refinement
1. `POST /api/fs/{id}/refine` (mode: auto/targeted/full) runs the refinement pipeline.
2. Returns: original score, refined score, improvement delta, refined text, diff lines, suggestions.
3. User reviews side-by-side diff on `/documents/[id]/refine`.
4. `POST /api/fs/{id}/refine/accept` persists refined text as a new `FSVersion`.
5. If the source document was already `COMPLETE`, the status is **kept**
   (no demotion to `PARSED`) and `analysis_stale` is flipped to `true`.
   The detail page renders an amber "FS was refined since last analysis
   — re-analyze to refresh metrics" banner with a one-click
   **Re-analyze** button. The Build CTAs stay visible immediately. The
   next successful analyze clears `analysis_stale` back to `false`.

### Accept/Resolve Workflow
1. **Edge cases**: `POST /{id}/edge-cases/{eid}/accept` merges `suggested_addition` into
   `parsed_text` at the target section, creates a new version, marks resolved.
2. **Contradictions**: `POST /{id}/contradictions/{cid}/accept` merges `suggested_resolution`
   into `parsed_text` at section A, creates a version, marks resolved.
3. **Ambiguities**: Only `PATCH /{id}/ambiguities/{fid}` to mark resolved (no text merge --
   ambiguities have clarification questions, not fix suggestions).
4. **Bulk**: `/bulk-accept` and `/bulk-resolve` endpoints process all unresolved items at once.
5. Quality score updates live after every mutation (completeness, clarity, consistency).

### Change Impact
1. `POST /api/fs/{id}/version` uploads a new version.
2. Impact pipeline: `version_node -> impact_node -> rework_node`.
3. Section-level diff (95% similarity threshold).
4. LLM classifies task impact: INVALIDATED / REQUIRES_REVIEW / UNAFFECTED.
5. Rework cost estimated deterministically (LOW=0.5d, MEDIUM=2d, HIGH=5d).

### Legacy Code Reverse FS
1. `POST /api/code/upload` uploads a ZIP codebase.
2. Code parser extracts entities (Python AST + regex for JS/TS/Java/Go).
3. 4-step LLM pipeline: module summaries -> user flows -> FS sections -> assembly.
4. Quality scoring with coverage and gap identification.
5. Generated FS can be imported as a new `FSDocument` for full analysis.

---

## 3. Analysis Pipeline -- Node Details

| Node | Purpose | Input | Output |
|------|---------|-------|--------|
| `parse_node` | Validate parsed sections | `parsed_sections` | Pass-through |
| `ambiguity_node` | LLM ambiguity detection per section | Sections | `ambiguity_flags` (severity, reason, question) |
| `debate_node` | CrewAI debate on HIGH flags | HIGH flags | `debate_results` (verdict, arguments) |
| `contradiction_node` | Pairwise section LLM comparison | Section pairs | `contradictions` (description, resolution) |
| `edge_case_node` | LLM gap/edge case detection | Sections | `edge_cases` (scenario, addition) |
| `quality_node` | Score computation + compliance tags | Issues | `quality_score` + `compliance_tags` |
| `task_decomposition_node` | LLM task breakdown | Sections | `tasks` (effort, criteria, tags) |
| `dependency_node` | LLM dependency inference + cycle detection | Tasks | `dependency_edges` + `task_order` |
| `traceability_node` | Deterministic task-section mapping | Tasks + sections | `traceability_entries` |
| `duplicate_node` | Qdrant similarity search | Sections | `duplicate_flags` |
| `testcase_node` | LLM test case generation | Tasks + criteria | `test_cases` |

Pipeline caching: When a `db` session is provided, each node checks `PipelineCacheDB` for a
matching `input_hash` and returns cached results without making LLM calls.

---

## 4. Adversarial Validation (CrewAI)

Runs on HIGH-severity ambiguity flags only:

1. **RedAgent** (Adversarial Requirements Analyst) -- argues the flag is a genuine ambiguity.
2. **BlueAgent** (Senior Implementation Architect) -- argues the flag is clear and unambiguous.
3. **ArbiterAgent** (Chief Requirements Arbiter) -- reads both arguments, issues JSON verdict.

Verdicts:
- **CLEAR** -- false positive, flag removed from results.
- **AMBIGUOUS** -- genuine, flag enriched with debate reasoning and confidence score.

---

## 5. Quality Score System

### Sub-Scores

| Metric | Formula | Weight |
|--------|---------|--------|
| **Completeness** | % of sections without unresolved edge-case gaps | 40% |
| **Clarity** | % of sections without unresolved ambiguity flags | 35% |
| **Consistency** | 1 - (unresolved contradictions / max section pairs) | 25% |
| **Overall** | Weighted sum of above three | -- |

All scores clamped to [0, 100]. Section indices are validated against the actual section count
to prevent out-of-range issues from inflating denominators.

### How Scores Improve

- **Accept edge case suggestion** -- merges text into document, marks resolved, completeness increases.
- **Accept contradiction resolution** -- merges text, marks resolved, consistency increases.
- **Resolve ambiguity** -- marks resolved, clarity increases.
- **Bulk accept/resolve** -- processes all unresolved items, scores can jump to 100.
- **Refine FS** -- LLM rewrites the entire document addressing all issues.

### Compliance Tags

Informational labels (PAYMENTS, AUTH, PII, EXTERNAL_API, SECURITY, DATA_RETENTION) that
flag sections needing special attention. These do not affect the quality score.

---

## 6. LLM Provider Configuration

### Generation
Four providers supported via `LLM_PROVIDER`:

| Provider | SDK | Example Model |
|----------|-----|---------------|
| `anthropic` | Native Anthropic | `claude-sonnet-4-20250514` |
| `openai` | Native OpenAI | `gpt-4o-mini` |
| `groq` | OpenAI-compatible | `llama-3.3-70b-versatile` |
| `openrouter` | OpenAI-compatible | `anthropic/claude-sonnet-4-20250514` |

All calls go through `backend/app/llm/client.py`. No other file imports LLM SDKs directly.

### Role-Based Model Routing (OpenRouter only)
Optional models for specific roles: `REASONING_MODEL`, `BUILD_MODEL`, `LONGCONTEXT_MODEL`,
`FALLBACK_MODEL`. Falls back to `PRIMARY_MODEL` when not set.

### Embeddings
Configured independently via `EMBEDDING_PROVIDER` and `EMBEDDING_MODEL`.
Default: OpenAI `text-embedding-3-small` (1536 dimensions).

---

## 7. JIRA and Confluence Integration

### JIRA (`POST /api/fs/{id}/export/jira`)
- Creates one Epic for the FS document.
- Creates one Story per task with title, description, acceptance criteria, effort.
- Returns epic + story keys/URLs.
- **Simulated mode** when `JIRA_URL` / `JIRA_API_TOKEN` are not set.

### Confluence (`POST /api/fs/{id}/export/confluence`)
- Creates a page with FS sections, quality score, ambiguity summary, task table, traceability.
- Returns page URL.
- **Simulated mode** when `CONFLUENCE_URL` / `CONFLUENCE_API_TOKEN` are not set.

### Report Exports
- `GET /api/fs/{id}/export/pdf/download` -- Styled PDF via reportlab (text fallback).
- `GET /api/fs/{id}/export/docx/download` -- Word document via python-docx (text fallback).
- `GET /api/fs/{id}/test-cases/csv` -- Test cases as CSV.

---

## 8. Complete API Reference

### Health
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | DB, Qdrant, LLM composite health |

### Document Management (`/api/fs`)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload` | Upload FS document (PDF/DOCX/TXT) |
| `GET` | `/` | List all documents |
| `GET` | `/{id}` | Document detail with sections |
| `GET` | `/{id}/status` | Lightweight status |
| `DELETE` | `/{id}` | Soft-delete |
| `POST` | `/{id}/reset-status` | Reset stuck processing |
| `POST` | `/{id}/parse` | Parse into sections + embed |
| `PATCH` | `/{id}/sections/{idx}` | Edit section heading/content |
| `POST` | `/{id}/sections` | Add new section |

### Analysis (`/api/fs`)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/{id}/analysis-progress` | Real-time pipeline node status |
| `POST` | `/{id}/analyze` | Run full 11-node pipeline |
| `POST` | `/{id}/cancel-analysis` | Cancel in-flight analysis |
| `GET` | `/{id}/ambiguities` | List ambiguity flags |
| `PATCH` | `/{id}/ambiguities/{fid}` | Resolve ambiguity |
| `POST` | `/{id}/ambiguities/bulk-resolve` | Bulk resolve all |
| `GET` | `/{id}/contradictions` | List contradictions |
| `PATCH` | `/{id}/contradictions/{cid}` | Resolve contradiction |
| `POST` | `/{id}/contradictions/{cid}/accept` | Accept resolution (merge text) |
| `POST` | `/{id}/contradictions/bulk-accept` | Bulk accept all resolutions |
| `POST` | `/{id}/contradictions/bulk-resolve` | Bulk resolve all |
| `GET` | `/{id}/edge-cases` | List edge case gaps |
| `PATCH` | `/{id}/edge-cases/{eid}` | Resolve edge case |
| `POST` | `/{id}/edge-cases/{eid}/accept` | Accept suggestion (merge text) |
| `POST` | `/{id}/edge-cases/bulk-accept` | Bulk accept all suggestions |
| `POST` | `/{id}/edge-cases/bulk-resolve` | Bulk resolve all |
| `GET` | `/{id}/quality-score` | Quality dashboard (scores + issues) |
| `GET` | `/{id}/quality-score/refresh` | Recompute from DB |
| `GET` | `/{id}/debate-results` | Debate transcripts |

### Refinement (`/api/fs`)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/{id}/refine` | Run refinement (auto/targeted/full) |
| `POST` | `/{id}/refine/accept` | Persist refined text as new version |

### Tasks and Dependencies (`/api/fs`)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/{id}/tasks` | List decomposed tasks |
| `GET` | `/{id}/tasks/{tid}` | Task detail |
| `PATCH` | `/{id}/tasks/{tid}` | Update task |
| `GET` | `/{id}/tasks/dependency-graph` | Dependency graph |
| `GET` | `/{id}/traceability` | Traceability matrix |

### Versions and Impact (`/api/fs`)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/{id}/version` | Upload new version + diff + impact |
| `GET` | `/{id}/versions` | List versions |
| `GET` | `/{id}/versions/{vid}/text` | Version body text |
| `POST` | `/{id}/versions/{vid}/revert` | Revert to version |
| `GET` | `/{id}/versions/{vid}/diff` | Section-level diff |
| `GET` | `/{id}/impact/{vid}` | Full impact analysis |
| `GET` | `/{id}/impact/{vid}/rework` | Rework estimate |

### Build Engine (`/api/fs`)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/{id}/build-state` | Create/reset build state |
| `GET` | `/{id}/build-state` | Current build progress |
| `PATCH` | `/{id}/build-state` | Update progress |
| `POST` | `/{id}/file-registry` | Register created file |
| `GET` | `/{id}/file-registry` | List files (filter by task/section) |
| `GET` | `/{id}/tasks/{tid}/context` | Aggregated task build context |
| `GET` | `/{id}/tasks/{tid}/verify` | Heuristic task verification |
| `POST` | `/{id}/place-requirement` | Find best section for new requirement |
| `GET` | `/{id}/pre-build-check` | Pre-build quality gate |
| `GET` | `/{id}/post-build-check` | Post-build coverage check |
| `POST` | `/{id}/snapshots` | Save rollback snapshot |
| `POST` | `/{id}/snapshots/{sid}/rollback` | Restore from snapshot |
| `GET` | `/{id}/pipeline-cache` | Cached node results |
| `DELETE` | `/{id}/pipeline-cache` | Clear cache |
| `GET` | `/{id}/build-prompt` | Generate structured build prompt |

### MCP Monitoring (`/api/mcp`)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions` | Create session |
| `GET` | `/sessions` | List sessions |
| `GET` | `/sessions/{sid}` | Get session |
| `POST` | `/sessions/{sid}/events` | Append event |
| `GET` | `/sessions/{sid}/events` | List events |
| `GET` | `/sessions/{sid}/events/stream` | SSE stream |

### Collaboration (`/api/fs`)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/{id}/sections/{idx}/comments` | Add comment with @-mentions |
| `GET` | `/{id}/comments` | List comments |
| `PATCH` | `/{id}/comments/{cid}/resolve` | Resolve comment |

### Approval (`/api/fs`)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/{id}/submit-for-approval` | Submit for review |
| `POST` | `/{id}/approve` | Approve with comment |
| `POST` | `/{id}/reject` | Reject with comment |
| `GET` | `/{id}/approval-status` | Status + history |

### Exports (`/api/fs`)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/{id}/export/jira` | Export to JIRA |
| `POST` | `/{id}/export/confluence` | Publish to Confluence |
| `GET` | `/{id}/test-cases` | List test cases |
| `GET` | `/{id}/test-cases/csv` | CSV download |
| `GET` | `/{id}/export/pdf` | PDF metadata |
| `GET` | `/{id}/export/pdf/download` | PDF download |
| `GET` | `/{id}/export/docx` | DOCX metadata |
| `GET` | `/{id}/export/docx/download` | DOCX download |

### Legacy Code (`/api/code`)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload` | Upload ZIP codebase |
| `POST` | `/{id}/generate-fs` | Generate FS from code |
| `GET` | `/{id}/generated-fs` | Generated FS sections |
| `GET` | `/{id}/report` | Quality report |
| `GET` | `/uploads` | List uploads |
| `GET` | `/{id}` | Upload detail |

### Other Routes
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/fs/{id}/duplicates` | Cross-doc duplicate flags |
| `GET` | `/api/library/search` | Semantic library search |
| `GET` | `/api/library/{item_id}` | Library item detail |
| `POST` | `/api/fs/{id}/suggestions` | Similar requirements |
| `GET` | `/api/fs/{id}/audit-log` | Audit event log |
| `GET` | `/api/activity-log` | Global activity feed |
| `POST/GET/PATCH/DELETE` | `/api/projects/...` | Project CRUD |

---

## 9. Frontend Pages

| Route | Purpose | Key Features |
|-------|---------|-------------|
| `/` | Dashboard | KPI cards, recent documents, feature cards |
| `/upload` | Upload | Drag-and-drop, project assignment, progress bar |
| `/documents` | Document list | Search, status badges, delete with confirm modal |
| `/documents/[id]` | Document detail | Sections (editable), analysis summary, pipeline actions, auto-analyze on return |
| `/documents/[id]/ambiguities` | Ambiguity analysis | Severity filter tabs, debate transcripts, resolve, bulk resolve all |
| `/documents/[id]/quality` | Quality dashboard | Gauge + sub-scores, contradictions (accept/resolve/bulk), edge cases (accept/resolve/bulk), compliance tags |
| `/documents/[id]/refine` | FS refinement | Before/after diff, accept/reject, version history with revert |
| `/documents/[id]/tasks` | Task board | Expandable cards, dependency graph, traceability tabs |
| `/documents/[id]/impact` | Impact analysis | Version upload/timeline, diff viewer, task impact, rework estimate |
| `/documents/[id]/traceability` | Traceability | Section-task matrix, orphan warnings, coverage % |
| `/documents/[id]/collab` | Collaboration | Comments, approval workflow, audit timeline |
| `/monitoring` | Monitoring | Activity log, MCP build sessions with auto-refresh |
| `/reverse` | Reverse FS | Code upload, FS generation, quality report |
| `/library` | Library | Semantic search with debounce |
| `/projects` | Projects | CRUD with document count KPIs |
| `/projects/[id]` | Project detail | Editable name/description, document upload, status grid |

### Shared Components
`PageShell`, `Badge`/`StatusBadge`, `KpiCard`, `AnimatedNumber`, `ScoreBar`, `QualityGauge`,
`Tabs`, `EmptyState`, `SearchInput`, `Modal`, `CopyButton`, `AnalysisProgress`,
`LoadingSkeleton`, `MotionWrap` (PageMotion/StaggerList/FadeIn)

---

## 10. MCP Server

Located in `mcp-server/`. Wraps the FastAPI backend for AI coding agents.

### Tools (20+)
| Category | Tools |
|----------|-------|
| Documents | `get_document`, `get_sections`, `upload_document` |
| Analysis | `run_analysis`, `get_ambiguities`, `resolve_ambiguity`, `get_quality_score`, `refine_fs` |
| Tasks | `get_tasks`, `get_task`, `update_task_status`, `get_dependency_graph`, `get_traceability` |
| Build | `get_build_state`, `update_build_state`, `create_build_state`, `register_file`, `get_files_for_task`, `get_files_for_section`, `pre_build_check`, `post_build_check`, `create_snapshot`, `rollback_to_snapshot`, `clear_pipeline_cache`, `get_pipeline_cache_status`, `check_library_for_reuse` |
| Impact | `upload_version`, `get_impact_analysis`, `get_version_diff` |
| Collaboration | `add_comment`, `get_comments` |
| Exports | `export_to_jira`, `export_to_confluence`, `get_test_cases` |
| Reverse | `upload_codebase`, `generate_fs_from_code` |

### Resources
- `fs_document` -- Full document context for AI agents
- `task_board` -- Task list for the agent

### Autonomous Build Protocol
The `start_build_loop` prompt defines a 7-phase protocol:
1. Pre-flight (state check, quality gate, library reuse scan)
2. Audit (fetch all analysis data in parallel)
3. Clear blockers (resolve HIGH ambiguities, refresh scores)
4. Build plan (generate manifest, confirm)
5. Build (implement tasks in dependency order, register files)
6. Checkpoint (every 5 tasks: verify quality, traceability)
7. Verify and export (post-build check, JIRA/PDF export)

### Setup
```bash
pip install -r mcp-server/requirements.txt
cd mcp-server && python server.py
```

See `mcp-server/README.md` for Cursor, Claude Desktop, and Claude Code configuration.

---

## 11. Configuration Reference

### LLM
| Variable | Values | Default |
|----------|--------|---------|
| `LLM_PROVIDER` | `anthropic`, `openai`, `groq`, `openrouter` | `anthropic` |
| `ANTHROPIC_API_KEY` | API key | -- |
| `OPENAI_API_KEY` | API key | -- |
| `GROQ_API_KEY` | API key | -- |
| `OPENROUTER_API_KEY` | API key | -- |
| `PRIMARY_MODEL` | Model name | `claude-sonnet-4-20250514` |
| `REASONING_MODEL` | OpenRouter role model | -- |
| `BUILD_MODEL` | OpenRouter role model | -- |
| `LONGCONTEXT_MODEL` | OpenRouter role model | -- |
| `FALLBACK_MODEL` | OpenRouter role model | -- |

### Embeddings
| Variable | Values | Default |
|----------|--------|---------|
| `EMBEDDING_PROVIDER` | `openai`, `groq`, `openrouter` | `openai` |
| `EMBEDDING_MODEL` | Model name | `text-embedding-3-small` |

### Database
| Variable | Default |
|----------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://fsp_user:fsp_secret@localhost:5434/fsplatform` |
| `DATABASE_URL_SYNC` | (sync variant for scripts) |
| `QDRANT_URL` | `http://localhost:6336` |
| `QDRANT_API_KEY` | -- |

### Integrations (Optional)
| Variable | Note |
|----------|------|
| `JIRA_URL` | Simulated when empty |
| `JIRA_EMAIL` | -- |
| `JIRA_API_TOKEN` | -- |
| `JIRA_PROJECT_KEY` | Default: `FSP` |
| `CONFLUENCE_URL` | Simulated when empty |
| `CONFLUENCE_EMAIL` | -- |
| `CONFLUENCE_API_TOKEN` | -- |
| `CONFLUENCE_SPACE_KEY` | Default: `FSP` |

### MCP Guards
| Variable | Default |
|----------|---------|
| `MCP_MONITORING_ENABLED` | `true` |
| `MCP_REQUIRE_ZERO_HIGH_AMBIGUITIES` | `true` |
| `MCP_MIN_QUALITY_SCORE` | `80` |
| `MCP_REQUIRE_TRACEABILITY` | `true` |
| `MCP_DRY_RUN_DEFAULT` | `false` |

### Application
| Variable | Default |
|----------|---------|
| `ENVIRONMENT` | `local` |
| `UPLOAD_DIR` | `uploads` |
| `MAX_UPLOAD_SIZE_MB` | `20` |
| `CORS_ALLOW_ORIGINS` | `http://localhost:3001` |

### Reverse FS Tuning
| Variable | Default | Purpose |
|----------|---------|---------|
| `REVERSE_LARGE_UPLOAD_ENABLED` | `false` | Allow large archives |
| `REVERSE_MAX_ARCHIVE_SIZE_MB` | `100` | Max compressed size |
| `REVERSE_MAX_UNCOMPRESSED_MB` | `500` | Max uncompressed size |
| `REVERSE_MAX_ARCHIVE_FILES` | `5000` | Max files in archive |
| `REVERSE_INCLUDE_EXTENSIONS` | `.py,.js,.ts,...` | File types to parse |
| `REVERSE_MAX_FILES_TO_PARSE` | `200` | Limit parsed files |
| `REVERSE_MAX_FILE_SIZE_BYTES` | `100000` | Skip large files |
| `REVERSE_TOP_FILES_INITIAL` | `30` | Initial selection |
| `REVERSE_TOP_FILES_MAX` | `60` | Max after expansion |
| `REVERSE_MAX_ENTITIES_PER_FILE` | `20` | Entity extraction cap |
| `REVERSE_MAX_CODE_EXCERPT_CHARS` | `500` | Code snippet length |
| `REVERSE_MIN_ACCEPTABLE_FLOWS` | `3` | Minimum user flows |

---

## 12. Quick Start

```bash
# 1. Configure
cp .env.example .env
# Edit .env with at least one LLM key + embedding key

# 2. Infrastructure
docker compose up -d postgres qdrant

# 3. Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 4. Frontend
cd frontend
npm install
npm run dev

# 5. Open http://localhost:3001
# Upload -> Parse -> Analyze -> Explore -> Refine -> Export
```

### Full Docker
```bash
docker compose up -d
# Backend: http://localhost:8000
# Frontend: http://localhost:3001
```

---

## 13. Testing

```bash
cd backend
python -m pytest tests/ -v
```

Test files cover all levels:

| File | Coverage |
|------|----------|
| `test_upload.py` | Upload, CRUD, health (L1) |
| `test_parser.py` | Parsing, chunking (L2) |
| `test_ambiguity.py` | Ambiguity detection, pipeline (L3) |
| `test_deep_analysis.py` | Contradictions, edge cases, quality (L4) |
| `test_task_decomposition.py` | Tasks, dependencies, traceability (L5) |
| `test_debate.py` | Adversarial debate (L6) |
| `test_impact.py` | Change impact, rework (L7) |
| `test_reverse.py` | Code parsing, reverse FS (L8) |
| `test_l9_semantic_collab.py` | Duplicates, library, collaboration (L9) |
| `test_l10_integrations.py` | JIRA, Confluence, exports, test cases (L10) |
| `test_build_engine.py` | Build state, registry, gates (Build engine) |
| `test_mcp_monitoring.py` | MCP sessions, events (MCP) |
| `test_e2e_full.py` | End-to-end full pipeline |
| `test_orchestration_routing.py` | Provider resolution, strict mode, fallback chain |

---

## 14. End-to-End Validation Guide

After uploading a real FS document, verify this checklist:

### A. Parse and Analyze
- Upload succeeds, document appears in list with `UPLOADED` status.
- Parse produces sections visible in the Sections tab.
- Analyze runs the full pipeline with progress stepper showing all nodes.
- Status transitions: `UPLOADED -> PARSED -> ANALYZING -> COMPLETE`.

### B. Ambiguities
- Flags appear with severity, reason, and clarification question.
- Resolve single flag updates UI immediately.
- Bulk "Resolve All" marks all as resolved.
- Debate transcripts appear for HIGH severity flags.

### C. Quality Dashboard
- Overall score and sub-scores (completeness, clarity, consistency) display.
- Contradictions tab: Accept resolution merges text and creates version.
- Edge cases tab: Accept suggestion merges text and creates version.
- Bulk Accept All / Mark All Resolved work for both tabs.
- Compliance tags appear grouped by type.
- Scores update live after every accept/resolve action.

### D. Refinement
- "Get suggestions" returns before/after scores and diff.
- Accept saves new version, **keeps `status = COMPLETE`**, and flips
  `analysis_stale = true`; the detail page renders the
  Re-analyze banner and Build CTAs remain visible.
- Re-analyze button runs the pipeline and clears `analysis_stale`.
- Version history shows all versions with view/revert.

### E. Tasks
- Tasks appear with effort, acceptance criteria, tags.
- Dependency graph shows connections.
- Traceability matrix links tasks to sections.

### F. Impact
- Upload new version produces diff.
- Task impact classified correctly.
- Rework estimate displayed.

### G. Collaboration
- Add comment succeeds and persists.
- Approval workflow transitions correctly.
- Audit trail records all events.

### H. Exports
- PDF/DOCX download links work.
- JIRA/Confluence export succeeds (simulated mode when unconfigured).
- Test cases CSV downloads.

### I. Cross-Page Sync
- Navigate to quality page, accept some issues, navigate back to detail page.
- Detail page shows updated unresolved counts and quality scores.

---

## 15. Operational Notes

- JIRA/Confluence run in **simulated mode** when credentials are not set.
- PDF/DOCX use `reportlab`/`python-docx` when available, text fallback otherwise.
- Adversarial debate only triggers on HIGH-severity flags to control LLM costs.
- Duplicate detection uses Qdrant cosine similarity > 0.88.
- Provider switching is hot: change `LLM_PROVIDER` in `.env` and restart backend.
- Pipeline caching skips LLM calls when `PipelineCacheDB` has a matching `input_hash`.
- `visibilitychange` listener ensures cross-page data freshness.
- Bulk accept creates ONE version with all merged changes (not one per item).

---

## 16. Research Contribution

> "DSPy-optimised ambiguity detection with adversarial multi-agent validation
> outperforms single-LLM approaches on enterprise FS documents -- measured
> against human-labelled ground truth."

- **Baseline**: Single GPT-4 call with manual prompt.
- **Proposed**: DSPy-optimised pipeline + CrewAI adversarial debate.
- **Evaluation**: Precision/recall of ambiguity flags vs human-annotated FS set.
- **Benchmark**: `backend/app/pipeline/benchmarks/debate_benchmark.py`

---

## 17. Build Engine -- Autonomous Build Support

The Build Engine turns the platform into a crash-resilient, autonomous product builder.

### Database Tables
| Table | Purpose |
|-------|---------|
| `BuildStateDB` | Build progress (phase, task index, completed/failed IDs, stack, output folder) |
| `FileRegistryDB` | Files mapped to tasks and sections |
| `BuildSnapshotDB` | Rollback snapshots of file registry + task states |
| `PipelineCacheDB` | Cached pipeline node results for skip-on-rehit |

### Autonomous Build Protocol (7 phases)
1. **Pre-flight** -- Check/resume build state, quality gate, pre-build validation, library reuse scan.
2. **Audit** -- Parallel fetch of quality, ambiguities, contradictions, tasks, dependencies.
3. **Clear Blockers** -- Resolve HIGH ambiguities, refresh scores.
4. **Build Plan** -- Generate manifest, show plan, wait for confirmation.
5. **Build** -- Implement tasks in dependency order, register files, persist state after each.
6. **Checkpoint** -- Every 5 tasks: verify quality, traceability, state persistence.
7. **Verify and Export** -- Post-build check must return GO before JIRA/PDF export.

### Future Change Protocol
1. Snapshot current state.
2. Place new requirement in best section.
3. Upload new version.
4. Impact analysis -- only affected files/tasks touched.
5. Post-build verify -- if quality drops >5 points, auto-rollback.

---

End of manual.
