# FS Intelligence Platform — Technical & User Manual

This manual reflects the current implementation across all 10 levels of the platform, including:
- Multi-step LangGraph analysis pipeline (11 nodes),
- Adversarial multi-agent validation (CrewAI),
- Multi-provider LLM support (Anthropic, OpenAI, Groq, OpenRouter),
- Full JIRA/Confluence integration with report exports,
- Semantic intelligence, collaboration, and audit trail.

---

## 1) System Overview

The FS Intelligence Platform is an AI-powered system that transforms Functional Specification (FS) documents into developer-ready work:

- **Upload** FS documents (PDF, DOCX, TXT) or legacy codebases (ZIP).
- **Analyze** — the LangGraph pipeline detects ambiguities, contradictions, edge cases, quality issues, and duplicates.
- **Decompose** — specs are broken into atomic dev tasks with effort, dependencies, and acceptance criteria.
- **Validate** — adversarial multi-agent debate (CrewAI) challenges ambiguity flags to reduce false positives.
- **Track** — traceability matrix links every task to its source section.
- **Export** — push tasks to JIRA, publish analysis to Confluence, download PDF/DOCX reports.
- **Reverse-generate** — ingest legacy codebases and generate FS documents from code.

Core design goal: **bridge the gap between functional teams (who write FS) and developer teams (who build from it)**.

---

## 2) End-to-End Data Flow

### Document Ingestion
1. Frontend uploads document to `POST /api/fs/upload`.
2. Parser extracts text (PDF via PyPDF, DOCX via python-docx, TXT direct).
3. Chunker splits content into section-aware chunks.
4. Dense embeddings are generated via configurable provider (OpenAI / Groq / OpenRouter).
5. Chunks + vectors + metadata are upserted into Qdrant.
6. Document metadata is stored in PostgreSQL.

### Analysis Pipeline (LangGraph)
1. `POST /api/fs/{id}/analyze` triggers the full 11-node pipeline:

```
parse_node → ambiguity_node → debate_node → contradiction_node →
edge_case_node → quality_node → task_decomposition_node →
dependency_node → traceability_node → duplicate_node → testcase_node
```

2. Each node reads from and writes to the shared `FSAnalysisState`.
3. Results are persisted to PostgreSQL (ambiguities, contradictions, edge cases, tasks, dependencies, traceability, test cases, duplicates, debate results).
4. Document status transitions: `PENDING → ANALYZING → COMPLETE`.

### Change Impact Analysis
1. Upload a new version of an existing FS document.
2. Separate impact pipeline: `version_node → impact_node → rework_node`.
3. Section-level diff (95% similarity) identifies changes.
4. LLM classifies task impact (INVALIDATED / REQUIRES_REVIEW / UNAFFECTED).
5. Rework cost is estimated deterministically.

### Legacy Code → FS Reverse Generation
1. Upload a ZIP codebase via `POST /api/code/upload`.
2. Code parser extracts entities (Python AST + regex for JS/TS/Java/Go).
3. 4-step LLM pipeline: module summaries → user flows → FS sections → assembly.
4. Quality scoring with coverage and gap identification.

---

## 3) Analysis Pipeline — Node Details

| Node | Level | Purpose |
|------|-------|---------|
| `parse_node` | L2 | Extract and chunk document text into sections |
| `ambiguity_node` | L3 | LLM-powered ambiguity detection with severity classification |
| `debate_node` | L6 | CrewAI adversarial debate on HIGH-severity ambiguity flags |
| `contradiction_node` | L4 | Pairwise section comparison for contradictory statements |
| `edge_case_node` | L4 | Identify edge cases, gaps, and missing error handling |
| `quality_node` | L4 | Score completeness, clarity, consistency; tag compliance areas |
| `task_decomposition_node` | L5 | Break sections into atomic dev tasks with effort + criteria |
| `dependency_node` | L5 | Build task dependency graph with cycle detection + topological sort |
| `traceability_node` | L5 | Link every task back to its source FS section |
| `duplicate_node` | L9 | Semantic duplicate detection across documents via Qdrant |
| `testcase_node` | L10 | LLM-powered test case generation with deterministic fallback |

---

## 4) Adversarial Validation (CrewAI)

The debate system runs on HIGH-severity ambiguity flags only:

1. **RedAgent** — argues the flag is a genuine ambiguity (attack).
2. **BlueAgent** — argues the flag is clear and unambiguous (defend).
3. **ArbiterAgent** — reads both arguments, issues a final verdict.

Verdicts:
- **CLEAR** — flag is a false positive, removed from results.
- **AMBIGUOUS** — flag is genuine, enriched with debate reasoning.

This reduces false-positive ambiguity flags and improves precision for developer handoff.

---

## 5) LLM Provider Configuration

### LLM Generation
The platform supports 4 providers, configured via `LLM_PROVIDER`:
- `anthropic` — Anthropic SDK (native), e.g. `claude-sonnet-4-20250514`
- `openai` — OpenAI SDK (native), e.g. `gpt-4o-mini`
- `groq` — Groq API (OpenAI-compatible), e.g. `llama-3.3-70b-versatile`
- `openrouter` — OpenRouter API (OpenAI-compatible), e.g. `anthropic/claude-sonnet-4-20250514`

All LLM calls go through `app/llm/client.py` — no other file imports an LLM SDK directly.

### Embeddings
Embeddings are configured independently via `EMBEDDING_PROVIDER`:
- `openai` — `text-embedding-3-small` (1536 dims)
- `groq` — `text-embedding-3-small`
- `openrouter` — `openai/text-embedding-3-small`

You can use one provider for LLM (e.g. Groq for speed) and another for embeddings (e.g. OpenAI for quality).

---

## 6) JIRA & Confluence Integration

### JIRA Export (`POST /api/fs/{id}/export/jira`)
- Creates one JIRA Epic for the FS document.
- Creates one JIRA Story per task with title, description, acceptance criteria, and effort.
- Returns epic + story keys/URLs.
- **Simulated mode**: if `JIRA_URL` / `JIRA_API_TOKEN` are not configured, returns mock responses for development.

### Confluence Export (`POST /api/fs/{id}/export/confluence`)
- Creates a Confluence page with full analysis:
  - FS sections, quality score, ambiguity summary, task table, traceability matrix.
- Returns page URL.
- **Simulated mode**: same as JIRA — returns mock responses when unconfigured.

### Report Exports
- `GET /api/fs/{id}/export/pdf` — Full intelligence report as styled PDF (via reportlab; text fallback).
- `GET /api/fs/{id}/export/docx` — Same as Word document (via python-docx; text fallback).
- `GET /api/fs/{id}/test-cases/csv` — Test cases exported as CSV.

---

## 7) API Endpoints

### Health
- `GET /health` — PostgreSQL, Qdrant, and LLM health with provider info.

### Document Management
- `POST /api/fs/upload` — Upload FS document (PDF/DOCX/TXT).
- `GET /api/fs/documents` — List all documents with status.
- `GET /api/fs/{id}` — Document detail with parsed sections.
- `DELETE /api/fs/{id}` — Delete document and all related data.
- `GET /api/fs/{id}/status` — Document status.
- `POST /api/fs/{id}/parse` — Parse document into sections.
- `GET /api/fs/{id}/sections` — List parsed sections.

### Analysis
- `POST /api/fs/{id}/analyze` — Run full 11-node pipeline.
- `GET /api/fs/{id}/ambiguities` — List ambiguity flags.
- `PATCH /api/fs/{id}/ambiguities/{flag_id}` — Resolve an ambiguity flag.
- `GET /api/fs/{id}/contradictions` — List contradictions.
- `GET /api/fs/{id}/edge-cases` — List edge case gaps.
- `GET /api/fs/{id}/quality-score` — Quality score breakdown.
- `GET /api/fs/{id}/compliance` — Compliance tags.

### Tasks & Dependencies
- `GET /api/fs/{id}/tasks` — List decomposed tasks.
- `GET /api/fs/{id}/tasks/{task_id}` — Task detail.
- `PATCH /api/fs/{id}/tasks/{task_id}` — Update task.
- `GET /api/fs/{id}/dependency-graph` — Task dependency graph.
- `GET /api/fs/{id}/traceability` — Traceability matrix.

### Adversarial Debate
- `GET /api/fs/{id}/debate-results` — Debate transcripts and verdicts.

### Change Impact
- `POST /api/fs/{id}/versions` — Upload new version.
- `GET /api/fs/{id}/versions` — List versions.
- `GET /api/fs/{id}/versions/diff` — Section-level diff.
- `GET /api/fs/{id}/versions/impact` — Task impact analysis.
- `GET /api/fs/{id}/versions/rework` — Rework cost estimate.

### Legacy Code Reverse FS
- `POST /api/code/upload` — Upload ZIP codebase.
- `POST /api/code/{id}/generate-fs` — Generate FS from code.
- `GET /api/code/{id}/generated-fs` — Generated FS sections.
- `GET /api/code/{id}/report` — Quality & coverage report.
- `GET /api/code/uploads` — List uploaded codebases.
- `GET /api/code/{id}` — Codebase detail.

### Semantic Intelligence & Collaboration
- `GET /api/fs/{id}/duplicates` — Duplicate requirement flags.
- `GET /api/library/search` — Semantic search across requirement library.
- `POST /api/library/items` — Add item to library.
- `GET /api/fs/{id}/comments` — Section-level comments.
- `POST /api/fs/{id}/comments` — Add comment.
- `PATCH /api/fs/{id}/comments/{id}` — Resolve comment.
- `POST /api/fs/{id}/approval/submit` — Submit for approval.
- `PATCH /api/fs/{id}/approval/{id}` — Approve or reject.
- `GET /api/fs/{id}/approval` — Approval status.
- `GET /api/audit/{id}` — Audit trail events.

### Exports & Integrations
- `POST /api/fs/{id}/export/jira` — Export tasks to JIRA.
- `POST /api/fs/{id}/export/confluence` — Publish to Confluence.
- `GET /api/fs/{id}/test-cases` — List generated test cases.
- `GET /api/fs/{id}/test-cases/csv` — CSV export.
- `GET /api/fs/{id}/export/pdf` — PDF report metadata.
- `GET /api/fs/{id}/export/pdf/download` — Download PDF.
- `GET /api/fs/{id}/export/docx` — DOCX report metadata.
- `GET /api/fs/{id}/export/docx/download` — Download DOCX.

---

## 8) Configuration Reference

### LLM
| Variable | Values | Default |
|----------|--------|---------|
| `LLM_PROVIDER` | `anthropic`, `openai`, `groq`, `openrouter` | `anthropic` |
| `ANTHROPIC_API_KEY` | API key | — |
| `OPENAI_API_KEY` | API key | — |
| `GROQ_API_KEY` | API key | — |
| `OPENROUTER_API_KEY` | API key | — |
| `PRIMARY_MODEL` | Model name (provider-specific) | `claude-sonnet-4-20250514` |

### Embeddings
| Variable | Values | Default |
|----------|--------|---------|
| `EMBEDDING_PROVIDER` | `openai`, `groq`, `openrouter` | `openai` |
| `EMBEDDING_MODEL` | Model name | `text-embedding-3-small` |

### Databases
| Variable | Default |
|----------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://fsp_user:fsp_secret@localhost:5434/fsplatform` |
| `QDRANT_URL` | `http://localhost:6336` |

### Integrations (Optional)
| Variable | Default |
|----------|---------|
| `JIRA_URL` | — (simulated when empty) |
| `JIRA_EMAIL` | — |
| `JIRA_API_TOKEN` | — |
| `JIRA_PROJECT_KEY` | `FSP` |
| `CONFLUENCE_URL` | — (simulated when empty) |
| `CONFLUENCE_EMAIL` | — |
| `CONFLUENCE_API_TOKEN` | — |
| `CONFLUENCE_SPACE_KEY` | `FSP` |

### Application
| Variable | Default |
|----------|---------|
| `UPLOAD_DIR` | `uploads` |
| `MAX_UPLOAD_SIZE_MB` | `20` |

---

## 9) Frontend Pages

| Route | Purpose |
|-------|---------|
| `/` | Dashboard — document stats, recent documents, feature tiles |
| `/upload` | Upload FS documents |
| `/documents` | Document list with status indicators |
| `/documents/[id]` | Document detail — sections, analysis summary, actions |
| `/documents/[id]/ambiguities` | Ambiguity review — severity stats, resolve flow, debate transcripts |
| `/documents/[id]/quality` | Quality dashboard — SVG gauge, sub-scores, compliance tags |
| `/documents/[id]/tasks` | Task board — expandable cards, dependency tree, JIRA export |
| `/documents/[id]/traceability` | Traceability matrix — sections × tasks grid, orphan/gap warnings |
| `/documents/[id]/impact` | Impact dashboard — version diff, task impact list, rework estimate |
| `/documents/[id]/collab` | Collaboration — comments, approval workflow, audit timeline |
| `/analysis` | Analysis overview across all documents |
| `/library` | Requirement library — semantic search, add/browse items |
| `/reverse` | Legacy code — upload ZIP, generate FS, quality report |

---

## 10) Project Structure

```text
fs-platform/
├── CONTEXT.md                  # Master project context
├── roadmap/                    # Per-level context files (CONTEXT_L1..L10)
├── docker-compose.yml          # 4 services: Postgres, Qdrant, Backend, Frontend
├── .env / .env.example
│
├── backend/
│   ├── app/
│   │   ├── api/                # 12 FastAPI routers (60+ endpoints)
│   │   ├── pipeline/
│   │   │   ├── graph.py        # LangGraph pipeline builder
│   │   │   ├── state.py        # FSAnalysisState TypedDict
│   │   │   └── nodes/          # 11 pipeline nodes + impact/reverse nodes
│   │   ├── agents/             # CrewAI debate agents (Red/Blue/Arbiter)
│   │   ├── integrations/       # JIRA + Confluence clients
│   │   ├── parsers/            # PDF/DOCX/TXT parsers + chunker + code parser
│   │   ├── llm/                # Unified multi-provider LLM client
│   │   ├── models/             # Pydantic schemas
│   │   ├── db/                 # SQLAlchemy models + async engine
│   │   ├── vector/             # Qdrant client + fs_store + embeddings
│   │   ├── config.py           # Centralized settings
│   │   └── main.py             # FastAPI entrypoint
│   ├── tests/                  # 329 tests across 10 test files
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── app/                # 13 Next.js pages (App Router)
│   │   ├── components/         # Shared UI components
│   │   └── lib/api.ts          # TypeScript API client (60+ functions)
│   ├── Dockerfile
│   └── package.json
```

---

## 11) End-to-End UI Validation Guide

Use this checklist after uploading a real FS to verify that the full product flow is working correctly.

### A) Ambiguities Page

**What this page does**
- Displays requirement statements flagged as ambiguous or unclear.
- Shows severity (`HIGH`, `MEDIUM`, `LOW`), reason, and clarification prompts.
- Supports resolving ambiguity flags.

**What to verify**
- Page loads successfully with no API error.
- Ambiguities list appears (or a valid empty state is shown).
- Resolving a flag updates the UI and persists after refresh.

### B) Quality Page

**What this page does**
- Shows overall quality score and sub-scores (clarity, completeness, consistency).
- Surfaces contradictions, edge cases, and compliance tags.

**What to verify**
- Score cards render correctly.
- Contradictions and edge-case sections load (or show clean empty states).
- Quality values are consistent with detected ambiguity/analysis outputs.

### C) Tasks Page

**What this page does**
- Shows developer tasks generated from FS sections.
- Includes effort, acceptance criteria, tags, and dependency metadata.

**What to verify**
- Meaningful FS inputs produce non-empty tasks.
- Task fields are readable and implementation-ready.
- Task totals match related views (especially traceability).

### D) Traceability Page

**What this page does**
- Maps generated tasks back to source FS sections.
- Highlights requirement-to-task coverage.

**What to verify**
- Matrix/table loads successfully.
- `total_tasks` aligns with the Tasks page count.
- Entries reference correct section headings/indices.

### E) Collaboration (Collab) Page

**What this page does**
- Provides section-level discussion and lightweight review workflows.
- Supports adding/resolving comments and visibility of collaboration state.

**What to verify**
- Add one comment successfully.
- New comment appears immediately and remains after refresh.
- Resolution state changes are reflected correctly in the UI.

### F) Impact Page (Version Upload)

**What this page does**
- Compares a newly uploaded FS version against the previous one.
- Shows changed sections, affected tasks, and rework estimate.

**What to verify**
- Uploading a new version succeeds.
- Version history updates.
- Impact and rework panels render with expected diff signals.

### G) Exports (PDF/DOCX + Jira/Confluence)

**What this page does**
- **PDF/DOCX**: Generates downloadable analysis reports.
- **Jira export**: Creates epic/story payloads for tasks.
- **Confluence export**: Creates a documentation page payload with analysis summary.
- Jira/Confluence run in simulated mode when not fully configured.

**What to verify**
- PDF and DOCX export actions return metadata/download links.
- Download endpoints return a file successfully.
- Jira/Confluence export actions succeed in simulated mode when credentials are absent.

### H) Final Pass Criteria (GO/NO-GO)

Mark the run as **GO** when all are true:
- All listed pages load and remain stable.
- No server-side 500 errors in the tested flows.
- Tasks, traceability, and analysis counts are internally consistent.
- Comment add/resolve, version upload, and exports complete successfully.
- Negative path checks (for example analyze-before-parse) return clear user-facing errors.

---

## 12) Quick Start

1. **Configure environment**
   ```bash
   cp .env.example .env
   ```
   Set at least one LLM API key and one embedding API key.

2. **Start infrastructure**
   ```bash
   docker compose up -d postgres qdrant
   ```

3. **Install backend dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. **Initialize database**
   ```bash
   python -c "from app.db.base import init_db; import asyncio; asyncio.run(init_db())"
   ```

5. **Start backend**
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

6. **Install frontend dependencies**
   ```bash
   cd frontend
   npm install
   ```

7. **Start frontend**
   ```bash
   npm run dev
   ```

8. **Open** `http://localhost:3001`

9. **Upload** an FS document → **Analyze** → explore ambiguities, tasks, quality, traceability.

---

## 13) Testing

```bash
cd backend
python -m pytest tests/ -v
```

329 tests across 10 test files covering:
- Upload/CRUD (L1)
- Document parsing (L2)
- Ambiguity detection + pipeline (L3)
- Deep analysis: contradictions, edge cases, quality (L4)
- Task decomposition + dependencies + traceability (L5)
- Adversarial debate (L6)
- Change impact analysis (L7)
- Legacy code reverse FS (L8)
- Semantic intelligence + collaboration (L9)
- Integrations + exports (L10)

---

## 14) Operational Notes

- If the health endpoint shows LLM as `unconfigured`, set the API key matching your `LLM_PROVIDER`.
- JIRA/Confluence exports operate in **simulated mode** when API credentials are not set — this is safe for development.
- PDF/DOCX reports use `reportlab`/`python-docx` when available, falling back to plain text reports.
- The adversarial debate only triggers on HIGH-severity ambiguity flags to avoid unnecessary LLM costs.
- Duplicate detection uses Qdrant cosine similarity > 0.88 across all ingested documents.
- Provider switching is hot — change `LLM_PROVIDER` in `.env` and restart the backend.
- Reverse FS supports a hybrid large-archive mode:
  - Normal path still honors `MAX_UPLOAD_SIZE_MB`.
  - When `REVERSE_LARGE_UPLOAD_ENABLED=true`, larger archives are accepted up to `REVERSE_MAX_ARCHIVE_SIZE_MB`.
  - Archive safety guards enforce `REVERSE_MAX_UNCOMPRESSED_MB` and `REVERSE_MAX_ARCHIVE_FILES`.
- Reverse parser/generation knobs for quality-vs-cost tuning:
  - `REVERSE_MAX_FILES_TO_PARSE`, `REVERSE_MAX_FILE_SIZE_BYTES`, `REVERSE_INCLUDE_EXTENSIONS`
  - `REVERSE_TOP_FILES_INITIAL`, `REVERSE_TOP_FILES_MAX`, `REVERSE_MAX_ENTITIES_PER_FILE`, `REVERSE_MAX_CODE_EXCERPT_CHARS`
  - `REVERSE_MIN_ACCEPTABLE_FLOWS` for automatic second-pass expansion when initial flow coverage is low.

---

## 15) Research Contribution

> "DSPy-optimised ambiguity detection with adversarial multi-agent validation outperforms single-LLM approaches on enterprise FS documents — measured against human-labelled ground truth."

- **Baseline**: Single GPT-4 call with manual prompt.
- **Proposed**: DSPy-optimised pipeline + CrewAI adversarial debate.
- **Evaluation**: Precision/recall of ambiguity flags vs human-annotated FS set.
- **Benchmark script**: `backend/app/agents/benchmark.py`

---

End of manual.
