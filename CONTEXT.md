# FS Intelligence Platform — Master Context

## Project
AI-powered platform that transforms Functional Specification (FS) documents
into dev-ready task breakdowns — with ambiguity detection, contradiction
analysis, change impact analysis, and legacy code reverse documentation.

Built by: MTech Software Systems final semester team (Jio Platforms)
Status: Level 10 complete — ALL LEVELS DONE

---

## Problem Being Solved

The gap between functional teams (who write FS) and developer teams
(who build from it) causes:
- Misunderstood requirements → expensive rework
- Ambiguous specs → wrong builds
- FS changes mid-sprint → no one knows what breaks
- Old systems with zero documentation → maintenance guesswork

This platform sits between the FS and the developer — making handoff
dramatically faster, clearer, and traceable.

---

## Stack

| Layer               | Tech                          | Purpose                              |
|---------------------|-------------------------------|--------------------------------------|
| Document parsing    | LlamaIndex + Unstructured.io  | FS ingestion, legacy code parsing    |
| Pipeline            | LangGraph                     | Core stateful multi-step pipeline    |
| LLM interface       | LangChain                     | Model abstraction layer              |
| Ambiguity detection | DSPy                          | Optimised prompt pipeline            |
| Adversarial agents  | CrewAI                        | Two-agent debate on ambiguities      |
| Semantic search     | Qdrant                        | Duplicate detection, req library     |
| Relational store    | PostgreSQL                    | Versions, audit trail, traceability  |
| Backend             | FastAPI                       | All API endpoints                    |
| Frontend            | React + TypeScript            | UI for functional and dev teams      |
| Deployment          | Docker + Docker Compose       | Containerisation                     |

LLM: claude-sonnet-4-20250514 (primary) — switchable via LLM_PROVIDER env var
Embeddings: text-embedding-3-small via OpenAI (or equivalent)

---

## Project Structure

```
fs-platform/
├── CONTEXT.md                  ← YOU ARE HERE (always keep updated)
├── roadmap/
│   ├── CONTEXT_L1.md
│   ├── CONTEXT_L2.md
│   ├── CONTEXT_L3.md
│   ├── CONTEXT_L4.md
│   ├── CONTEXT_L5.md
│   ├── CONTEXT_L6.md
│   ├── CONTEXT_L7.md
│   ├── CONTEXT_L8.md
│   ├── CONTEXT_L9.md
│   └── CONTEXT_L10.md
├── backend/
│   ├── app/
│   │   ├── api/            ← FastAPI routers
│   │   ├── pipeline/       ← LangGraph pipeline nodes
│   │   ├── agents/         ← CrewAI agents
│   │   ├── parsers/        ← LlamaIndex + Unstructured parsers
│   │   ├── models/         ← Pydantic models
│   │   ├── db/             ← PostgreSQL (SQLAlchemy)
│   │   ├── vector/         ← Qdrant client
│   │   └── config.py
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/            ← Next.js App Router pages
│   │   ├── components/
│   │   └── lib/            ← API client functions
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
├── .env
└── .env.example
```

---

## Conventions

- ALL pipeline nodes are async
- ALL inter-node data uses Pydantic models (no raw dicts)
- ALL LLM calls go through backend/app/llm/client.py only
- ALL external calls wrapped in try/except with graceful fallback
- Type hints on every function
- No print() anywhere — use Python logging
- No hardcoded strings — always use settings or constants
- API responses always follow { data, error, meta } envelope

---

## Key Design Decisions

1. LangGraph is the ONLY pipeline orchestrator — no mixing with LangChain chains
2. LangChain used ONLY as LLM interface wrapper (swap models easily)
3. DSPy handles ambiguity detection prompts — not manual prompt strings
4. CrewAI used ONLY for adversarial agent debate (L6) — not general orchestration
5. Qdrant for semantic search — Postgres for relational/structured data
6. Never use AutoGen — CrewAI covers the multi-agent need

---

## Level Map

| Level | Name                         | Status      |
|-------|------------------------------|-------------|
| L1    | Foundation                   | ✅ Completed |
| L2    | Document parsing             | ✅ Completed |
| L3    | Ambiguity detection          | ✅ Completed |
| L4    | Deep FS analysis             | ✅ Completed |
| L5    | Task decomposition           | ✅ Completed |
| L6    | Adversarial validation       | ✅ Completed |
| L7    | FS change impact analysis    | ✅ Completed |
| L8    | Legacy code → FS reverse gen | ✅ Completed |
| L9    | Semantic intelligence + collab | ✅ Completed |
| L10   | Integrations + polish        | ✅ Completed |

MTech viva scope: L1 through L7 (core pipeline complete)
Roadmap (post-viva): L8, L9, L10

---

## Research Contribution (MTech Thesis Angle)

"DSPy-optimised ambiguity detection with adversarial multi-agent
validation outperforms single-LLM approaches on enterprise FS documents
— measured against human-labelled ground truth."

Evaluation: precision/recall of ambiguity flags vs human-annotated FS set
Baseline: single GPT-4 call with manual prompt
Proposed: DSPy-optimised pipeline + CrewAI adversarial debate

---

## Progress Tracker

Last completed level: L10
Currently building: — (all levels complete)
Next: —

## Built
- L1: Full project skeleton, Docker Compose (4 services), FastAPI backend with async DB,
  file upload CRUD API, LLM client, Qdrant client, Next.js 14 frontend shell,
  health check endpoint, 8 passing pytest tests, end-to-end upload flow working
- L2: Document parsing pipeline (PDF/DOCX/TXT parsers), section-aware chunker,
  OpenAI embedding + Qdrant vector storage, POST /api/fs/{id}/parse endpoint,
  frontend sections accordion with expand/collapse, 18 new tests (26 total)
- L3: LangGraph pipeline (parse_node → ambiguity_node → END), LLM-powered ambiguity
  detection (gpt-4o-mini), AmbiguityFlagDB model, analysis API (analyze/list/resolve),
  multi-provider LLM client (OpenAI+Anthropic), frontend ambiguity review page with
  severity stats + progress bar + resolve flow, 13 new tests (39 total)
- L4: LangGraph pipeline extended (5 nodes: parse → ambiguity → contradiction →
  edge_case → quality → END), contradiction detection (pairwise LLM comparison),
  edge case gap detection, quality scorer (completeness/clarity/consistency),
  compliance tagging (payments/auth/PII/external_api/security/data_retention),
  3 new DB tables (contradictions/edge_case_gaps/compliance_tags),
  6 new API endpoints (GET/PATCH contradictions, edge-cases, quality-score),
  frontend quality dashboard (SVG gauge, sub-score bars, tabbed content),
  27 new tests (66 total)
- L5: LangGraph pipeline extended to 8 nodes (+ task_decomposition → dependency
  → traceability → END), LLM-powered task decomposition (sections → atomic dev
  tasks with acceptance criteria/effort/tags), dependency graph builder (LLM
  inference + DFS cycle detection + Kahn’s topological sort + parallel detection),
  traceability matrix node, 2 new DB tables (fs_tasks/traceability_entries),
  5 new API endpoints (GET/PATCH tasks, dependency-graph, traceability),
  frontend task board (expandable cards, dependency tree, traceability matrix),
  JIRA export placeholder, 29 new tests (95 total)
- L6: LangGraph pipeline extended to 9 nodes (+ debate_node after ambiguity_node),
  CrewAI adversarial debate system (RedAgent vs BlueAgent → ArbiterAgent),
  debate runs on HIGH severity ambiguity flags only, CLEAR verdicts remove
  false positives, AMBIGUOUS verdicts enrich flags with debate reasoning,
  DebateResultDB table, GET /api/fs/{id}/debate-results API endpoint,
  debate results persisted in analyze_document flow, benchmark script
  (precision/recall comparison with/without debate for thesis evaluation),
  frontend debate transcript UI (expandable Red/Blue/Arbiter panels,
  confidence bar, "Overridden by debate" section, summary banner),
  crewai added to stack, 25 new tests (120 total)
- L7: FS Change Impact Analysis — separate LangGraph impact pipeline
  (version_node → impact_node → rework_node → END), difflib-based section
  diff with 95% similarity threshold, LLM-powered task impact classification
  (INVALIDATED/REQUIRES_REVIEW/UNAFFECTED), deterministic rework cost estimator
  (effort_map: LOW=0.5d, MEDIUM=2d, HIGH=5d, UNKNOWN=2d), FSVersion extended
  with parsed_text/file_path/file_size, 3 new DB tables (fs_changes/task_impacts/
  rework_estimates), impact_router with 5 endpoints (POST version upload,
  GET versions/diff/impact/rework), frontend impact dashboard (version upload
  + selector, rework summary card with 4 metric tiles, expandable side-by-side
  diff view, color-coded task impact list sorted by severity), chunk_text_into_sections
  helper for old version re-chunking, 52 new tests (172 total)
- L8: Legacy Code → FS Reverse Generation — separate LangGraph reverse pipeline
  (reverse_fs_node → reverse_quality_node → END), code parser with Python AST
  extraction + regex-based JS/TS/Java/Go extraction, file filtering (node_modules,
  __pycache__, .git, venv, etc.), zip extraction with single-folder wrapper detection,
  4-step LLM reverse FS generation (module summaries → user flows → FS sections →
  assembly), deterministic quality scoring (coverage + confidence + gap identification),
  CodeUploadDB table with status tracking, code_router with 6 endpoints (POST upload,
  POST generate-fs, GET generated-fs/report/uploads/detail), frontend reverse FS
  dashboard (zip upload, codebase list with status badges, quality report card,
  gaps with LOW CONF badges, forward pipeline link, expandable sections viewer),
  8 new API schemas, 65 new tests (237 total)
- L9: Semantic Intelligence + Collaboration — Qdrant-powered duplicate
  requirement detection (cosine similarity > 0.88 across documents),
  reusable requirement library (auto-populated on approval, semantic search),
  section-level comment threads with @-mention extraction and resolution,
  approval workflow (submit → approve/reject) with auto-library-population,
  full audit trail (11 event types logged across upload/parse/analyze/version/
  comment/approval flows), 5 new DB tables (duplicate_flags/fs_comments/
  fs_mentions/fs_approvals/audit_events), 2 new enums (ApprovalStatus/
  AuditEventType), duplicate_node added to LangGraph analysis pipeline,
  3 new vector store functions (search_similar_sections/store_library_item/
  search_library), 5 new API routers with 14 endpoints, audit helper utility,
  existing routers updated with audit event logging, frontend library search
  page, collaboration page (comments + approval workflow + audit timeline),
  duplicate warning banner + approval badge on document detail page,
  43 new tests (280 total)
- L10: Integrations + Polish — JIRA export (JiraClient with epic+story creation,
  simulated mode for demo), Confluence export (ConfluenceClient with XHTML page
  builder, quality/ambiguity/task/traceability sections), LLM-powered test case
  generation (testcase_node as 11th pipeline node with deterministic fallback),
  TestCaseDB table + TestType enum, PDF report export (reportlab with styled
  tables + text fallback), Word report export (python-docx with structured
  tables + text fallback), CSV test case export, 8 JIRA/Confluence config
  settings, export_router with 10 endpoints, enhanced dashboard (status cards +
  recent docs grid + 6 feature tiles), traceability matrix UI (sections×tasks
  grid, orphaned task/uncovered section warnings), document detail page with
  traceability link, analysis_router updated to persist test cases,
  49 new tests (329 total)

## Current .env Variables Required
```
DATABASE_URL=postgresql://user:pass@localhost:5432/fsplatform
QDRANT_URL=http://localhost:6333
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
EMBEDDING_MODEL=text-embedding-3-small
PRIMARY_MODEL=claude-sonnet-4-20250514
# L10: Integrations (optional — simulated mode if not set)
JIRA_URL=https://your-org.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your_jira_token
JIRA_PROJECT_KEY=FSP
CONFLUENCE_URL=https://your-org.atlassian.net/wiki
CONFLUENCE_EMAIL=you@example.com
CONFLUENCE_API_TOKEN=your_confluence_token
CONFLUENCE_SPACE_KEY=FSP
```
