# ⚡ FS Intelligence Platform

AI-powered platform that transforms Functional Specification (FS) documents into developer-ready task breakdowns — with ambiguity detection, adversarial validation, contradiction analysis, change impact tracking, and legacy code reverse documentation.

Built as an MTech Software Systems final-semester project (Jio Platforms).

---

## Features

- 📄 **FS Document Ingestion** — Upload PDF, DOCX, or TXT specifications.
- 🔍 **Ambiguity Detection** — LLM-powered identification of vague, incomplete, or unclear requirements.
- ⚔️ **Adversarial Validation** — CrewAI multi-agent debate (Red vs Blue → Arbiter) reduces false-positive ambiguity flags.
- ⚡ **Contradiction & Edge Case Analysis** — Pairwise section comparison for conflicts and gap detection.
- 📊 **Quality Scoring** — Completeness, clarity, consistency metrics with compliance tagging.
- 🧩 **Task Decomposition** — Break specs into atomic dev tasks with effort estimation, acceptance criteria, and tags.
- 🔗 **Dependency Graph** — Task ordering with cycle detection and parallel-execution detection.
- 🗺️ **Traceability Matrix** — Link every task to its source FS section; highlight orphans and gaps.
- 📈 **Change Impact Analysis** — Upload FS versions, diff sections, classify task impact, estimate rework.
- 🔄 **Legacy Code → FS** — Upload codebases (ZIP), auto-generate functional specifications from source.
- 🔎 **Semantic Duplicate Detection** — Qdrant-powered similarity search across documents.
- 📚 **Requirement Library** — Reusable requirements with semantic search.
- 💬 **Collaboration** — Section-level comments, @-mentions, approval workflows, full audit trail.
- 🎫 **JIRA Export** — Push tasks as epics + stories to JIRA.
- 📝 **Confluence Export** — Publish full analysis reports as Confluence pages.
- 📑 **PDF/Word Reports** — Download styled intelligence reports.
- 🧪 **Test Case Generation** — LLM-powered test cases from acceptance criteria with CSV export.

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | FastAPI, Python 3.11+ | API layer, async throughout |
| Pipeline | LangGraph | Stateful 11-node analysis pipeline |
| LLM Interface | LangChain + direct SDKs | Multi-provider model abstraction |
| Ambiguity Detection | DSPy | Optimised prompt pipeline |
| Adversarial Agents | CrewAI | Two-agent debate on ambiguities |
| Semantic Search | Qdrant | Duplicate detection, requirement library |
| Relational Store | PostgreSQL | Versions, audit trail, traceability |
| Frontend | Next.js 14, TypeScript | 13-page App Router UI |
| Embeddings | OpenAI / Groq / OpenRouter | Configurable embedding provider |
| Reports | reportlab, python-docx | PDF and Word export |
| Deployment | Docker Compose | 4-service containerization |

### Supported LLM Providers
| Provider | Example Model | Env Variable |
|----------|--------------|--------------|
| Anthropic | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-4o-mini` | `OPENAI_API_KEY` |
| Groq | `llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| OpenRouter | `anthropic/claude-sonnet-4-20250514` | `OPENROUTER_API_KEY` |

---

## Documentation

- `docs/MANUAL.md` — Full technical manual: pipeline details, API reference, configuration, operational notes.
- `roadmap/CONTEXT_L1..L10.md` — Per-level implementation context files.
- `CONTEXT.md` — Master project context and progress tracker.

---

## Quick Start

### 1) Clone & Configure

```bash
git clone <repo-url>
cd fs_intelligence_platform
cp .env.example .env
```

Edit `.env` with your API keys. At minimum, set one LLM key:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
PRIMARY_MODEL=gpt-4o-mini

EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
```

### 2) Start Infrastructure

```bash
docker compose up -d postgres qdrant
```

This starts PostgreSQL (port 5434) and Qdrant (port 6336).

### 3) Install & Run Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 4) Install & Run Frontend

```bash
cd frontend
npm install
npm run dev
```

### 5) Open

Navigate to `http://localhost:3001` and:
1. Upload an FS document (PDF, DOCX, or TXT).
2. Click **Analyze** to run the full pipeline.
3. Explore ambiguities, quality scores, decomposed tasks, traceability matrix.
4. Export to JIRA or download PDF/DOCX report.

### Full Docker (All Services)

```bash
docker compose up -d
```

Backend on `http://localhost:8000`, Frontend on `http://localhost:3001`.

---

## Analysis Pipeline

The core analysis runs an 11-node LangGraph pipeline:

```text
parse → ambiguity → debate → contradiction → edge_case → quality →
task_decomposition → dependency → traceability → duplicate → testcase
```

| Node | What It Does |
|------|-------------|
| **parse** | Extract and chunk document into sections |
| **ambiguity** | Detect vague/incomplete requirements (severity: LOW/MEDIUM/HIGH) |
| **debate** | CrewAI adversarial debate on HIGH flags (Red → Blue → Arbiter) |
| **contradiction** | Find contradictory statements between sections |
| **edge_case** | Identify missing error handling, edge cases, gaps |
| **quality** | Score completeness/clarity/consistency, tag compliance areas |
| **task_decomposition** | Break sections into atomic dev tasks with effort + criteria |
| **dependency** | Build task graph, detect cycles, find parallel opportunities |
| **traceability** | Link every task to its source section |
| **duplicate** | Semantic search for duplicate requirements across documents |
| **testcase** | Generate test cases from acceptance criteria |

---

## API Surface

### Core
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health (DB, Qdrant, LLM) |
| `POST` | `/api/fs/upload` | Upload document |
| `GET` | `/api/fs/documents` | List documents |
| `POST` | `/api/fs/{id}/analyze` | Run analysis pipeline |

### Analysis Results
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/fs/{id}/ambiguities` | Ambiguity flags |
| `GET` | `/api/fs/{id}/contradictions` | Contradictions |
| `GET` | `/api/fs/{id}/edge-cases` | Edge case gaps |
| `GET` | `/api/fs/{id}/quality-score` | Quality metrics |
| `GET` | `/api/fs/{id}/tasks` | Decomposed tasks |
| `GET` | `/api/fs/{id}/traceability` | Traceability matrix |
| `GET` | `/api/fs/{id}/debate-results` | Debate transcripts |

### Change Impact
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/fs/{id}/versions` | Upload new version |
| `GET` | `/api/fs/{id}/versions/impact` | Task impact analysis |
| `GET` | `/api/fs/{id}/versions/rework` | Rework cost estimate |

### Exports
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/fs/{id}/export/jira` | Push to JIRA |
| `POST` | `/api/fs/{id}/export/confluence` | Publish to Confluence |
| `GET` | `/api/fs/{id}/export/pdf/download` | Download PDF report |
| `GET` | `/api/fs/{id}/export/docx/download` | Download Word report |
| `GET` | `/api/fs/{id}/test-cases/csv` | Download test cases CSV |

### Legacy Code
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/code/upload` | Upload ZIP codebase |
| `POST` | `/api/code/{id}/generate-fs` | Generate FS from code |
| `GET` | `/api/code/{id}/generated-fs` | Get generated FS |

Full endpoint list with payloads: see `docs/MANUAL.md`.

---

## Configuration

Most behavior is driven by `.env` and `backend/app/config.py`:

| Area | Key Variables |
|------|--------------|
| **LLM** | `LLM_PROVIDER` ∈ {`anthropic`, `openai`, `groq`, `openrouter`} |
| **Embeddings** | `EMBEDDING_PROVIDER` ∈ {`openai`, `groq`, `openrouter`} |
| **Models** | `PRIMARY_MODEL`, `EMBEDDING_MODEL` |
| **Database** | `DATABASE_URL`, `QDRANT_URL` |
| **JIRA** | `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` |
| **Confluence** | `CONFLUENCE_URL`, `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN` |

LLM and embedding providers are **independent** — use Groq for fast LLM inference and OpenAI for embeddings, for example.

See `.env.example` for the complete reference.

---

## Project Structure

```text
fs_intelligence_platform/
├── CONTEXT.md                    # Master project context
├── docker-compose.yml            # Postgres + Qdrant + Backend + Frontend
├── .env.example                  # Full configuration reference
│
├── backend/
│   ├── app/
│   │   ├── api/                  # 12 routers, 60+ endpoints
│   │   ├── pipeline/
│   │   │   ├── graph.py          # LangGraph pipeline
│   │   │   ├── state.py          # Shared pipeline state
│   │   │   └── nodes/            # 11 analysis + impact + reverse nodes
│   │   ├── agents/               # CrewAI debate (Red/Blue/Arbiter)
│   │   ├── integrations/         # JIRA + Confluence clients
│   │   ├── llm/                  # Multi-provider LLM client
│   │   ├── parsers/              # PDF/DOCX/TXT + code parsers
│   │   ├── vector/               # Qdrant store + embeddings
│   │   ├── db/                   # SQLAlchemy models
│   │   └── config.py             # Centralized settings
│   ├── tests/                    # 329 tests
│   └── requirements.txt
│
├── frontend/
│   ├── src/app/                  # 13 Next.js pages
│   ├── src/lib/api.ts            # TypeScript API client
│   └── package.json
│
├── roadmap/                      # CONTEXT_L1..L10.md
└── docs/MANUAL.md                # Technical manual
```

---

## Testing

```bash
cd backend
python -m pytest tests/ -v
```

**329 tests** across 10 test files, covering every level:

| Level | Tests | Coverage |
|-------|-------|----------|
| L1 | 8 | Upload, CRUD, health |
| L2 | 18 | Parsing, chunking |
| L3 | 13 | Ambiguity detection, pipeline |
| L4 | 27 | Contradictions, edge cases, quality |
| L5 | 29 | Tasks, dependencies, traceability |
| L6 | 25 | Adversarial debate |
| L7 | 52 | Change impact, rework |
| L8 | 65 | Code parsing, reverse FS |
| L9 | 43 | Duplicates, library, collaboration |
| L10 | 49 | JIRA, Confluence, exports, test cases |

---

## Research Contribution

> *"DSPy-optimised ambiguity detection with adversarial multi-agent validation outperforms single-LLM approaches on enterprise FS documents — measured against human-labelled ground truth."*

- **Baseline**: Single GPT-4 call with manual prompt.
- **Proposed**: DSPy-optimised pipeline + CrewAI adversarial debate.
- **Metric**: Precision/recall of ambiguity flags vs human-annotated FS document set.
- **Benchmark**: `backend/app/agents/benchmark.py`

---

## License

This project is an academic/internal reference implementation for MTech thesis evaluation.  
Add your chosen license before public or commercial deployment.
