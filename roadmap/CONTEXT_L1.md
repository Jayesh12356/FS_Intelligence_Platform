# CONTEXT_L1 — Foundation

## What This Level Builds
Complete project skeleton. Nothing AI yet — just the infrastructure
every subsequent level will build on top of.

## Goal
After L1, you can: run the project locally with docker-compose,
upload a file via API, get it back, and see a basic frontend shell.

---

## Build Order (8 prompts)

### Prompt 01 — Project skeleton + Docker
```
Create the full folder structure for the FS Intelligence Platform.
- backend/ with FastAPI app skeleton (app/__init__.py, app/main.py, app/config.py)
- frontend/ with Next.js 14 App Router (npx create-next-app)
- docker-compose.yml with services: backend (FastAPI), frontend (Next.js),
  postgres (postgres:16-alpine), qdrant (qdrant/qdrant:latest)
- .env.example with all required variables
- backend/requirements.txt with: fastapi, uvicorn, sqlalchemy, asyncpg,
  psycopg2-binary, python-dotenv, pydantic-settings, python-multipart, aiofiles
```

### Prompt 02 — PostgreSQL + SQLAlchemy setup
```
Set up PostgreSQL connection and base models.
- backend/app/db/base.py — SQLAlchemy async engine + session
- backend/app/db/models.py — Base tables:
    FSDocument: id, filename, original_text, parsed_text, status, created_at, updated_at
    FSVersion: id, fs_id (FK), version_number, content_hash, diff_summary, created_at
    AnalysisResult: id, fs_id (FK), analysis_type, result_json, created_at
- backend/app/db/init_db.py — create all tables on startup
- Alembic setup for migrations
```

### Prompt 03 — Config + settings
```
Set up pydantic-settings config.
- backend/app/config.py — Settings class with all env vars:
    DATABASE_URL, QDRANT_URL, LLM_PROVIDER, ANTHROPIC_API_KEY,
    OPENAI_API_KEY, EMBEDDING_MODEL, PRIMARY_MODEL
- Settings loaded once as singleton
- backend/app/main.py — FastAPI app with lifespan (db init on startup)
- CORS enabled for http://localhost:3000
```

### Prompt 04 — File upload API
```
Build file upload and storage endpoints.
- backend/app/api/fs_router.py:
    POST /api/fs/upload — accepts PDF, DOCX, TXT
        saves file to disk at uploads/{uuid}/original.*
        creates FSDocument row in postgres with status=UPLOADED
        returns { id, filename, status }
    GET /api/fs/{id} — returns FSDocument metadata
    GET /api/fs/ — list all uploaded documents
    DELETE /api/fs/{id} — soft delete
- Validate file type and size (max 20MB) on upload
- Standard response envelope: { data, error, meta }
```

### Prompt 05 — LLM client setup
```
Set up the unified LLM client.
- backend/app/llm/client.py:
    LLMClient class — wraps anthropic SDK
    call_llm(prompt, system, model=None) -> str — async
    Uses PRIMARY_MODEL from settings by default
    Raises LLMError on failure with structured logging
- backend/app/llm/__init__.py — exports get_llm_client() singleton
- No other file should import the SDK directly — always use this client
```

### Prompt 06 — Qdrant setup
```
Set up Qdrant vector store client.
- backend/app/vector/client.py:
    QdrantClient wrapper
    Collections to create on startup:
        fs_requirements — stores requirement embeddings (1536 dim)
        fs_library — stores reusable requirement patterns (1536 dim)
    create_collections() — idempotent, safe to call on every startup
- backend/app/vector/__init__.py
- Add Qdrant init to FastAPI lifespan in main.py
```

### Prompt 07 — Frontend shell
```
Build the basic Next.js frontend shell.
- frontend/src/app/layout.tsx — root layout with nav:
    Nav items: Upload FS | My Documents | Analysis
    Simple clean layout, dark/light mode support
- frontend/src/app/page.tsx — landing page:
    Hero: "Turn your FS into dev-ready tasks"
    Upload button → /upload
- frontend/src/app/upload/page.tsx — file upload page:
    Drag-and-drop file upload (PDF, DOCX, TXT)
    Calls POST /api/fs/upload
    On success: redirect to /documents/{id}
- frontend/src/lib/api.ts — typed API client functions
```

### Prompt 08 — Health checks + QA
```
Wire everything together and verify.
- GET /health — returns { status, db, qdrant, llm } (checks all connections)
- GET /api/fs/{id}/status — returns current processing status
- docker-compose up — all 4 services start cleanly
- Upload a test PDF — verify it appears in GET /api/fs/
- frontend loads at localhost:3001, nav renders, upload page works
- pytest tests/test_upload.py — basic upload and retrieval tests
```

---

## Files Created in L1

```
backend/
  app/
    __init__.py
    main.py
    config.py
    db/__init__.py, base.py, models.py, init_db.py
    api/__init__.py, fs_router.py, health_router.py
    models/__init__.py, schemas.py
    llm/__init__.py, client.py
    vector/__init__.py, client.py
  tests/__init__.py, conftest.py, test_upload.py
  requirements.txt
  pyproject.toml
  Dockerfile
frontend/
  src/app/layout.tsx, page.tsx, globals.css
  src/app/upload/page.tsx
  src/app/documents/page.tsx
  src/app/documents/[id]/page.tsx
  src/app/analysis/page.tsx
  src/lib/api.ts
  Dockerfile
docker-compose.yml
.env.example
.env
.gitignore
```

---

## Port Mapping (to avoid conflicts with existing projects)

| Service    | Host Port | Container Port |
|------------|-----------|----------------|
| Postgres   | 5434      | 5432           |
| Qdrant HTTP| 6336      | 6333           |
| Qdrant gRPC| 6337      | 6334           |
| Backend    | 8000      | 8000           |
| Frontend   | 3001      | 3000           |

---

## What L1 Does NOT Do
- No parsing of file content (that is L2)
- No AI calls (LLM client is set up but not called yet)
- No Qdrant writes (client is set up but no data yet)

---

## Built
- ✅ Project skeleton with docker-compose (4 services)
- ✅ PostgreSQL + SQLAlchemy async engine + 3 ORM models (FSDocument, FSVersion, AnalysisResult)
- ✅ Pydantic-settings config with singleton pattern
- ✅ File upload CRUD API (POST /api/fs/upload, GET /api/fs/, GET /api/fs/{id}, DELETE /api/fs/{id})
- ✅ Unified LLM client (Anthropic SDK wrapper with structured error handling)
- ✅ Qdrant vector client (idempotent collection creation, 1536-dim cosine)
- ✅ Next.js 14 frontend shell (landing, upload, documents list, document detail, analysis placeholder)
- ✅ Dark/light theme toggle with glassmorphism design system
- ✅ Health check endpoint (/health — DB, Qdrant, LLM status)
- ✅ 8 pytest tests — all passing
- ✅ Full end-to-end flow: upload → list → get → delete working via frontend and API

## Done When
- ✅ docker-compose up works with zero errors
- ✅ File upload API accepts PDF/DOCX/TXT and returns an ID
- ✅ Frontend renders and upload flow works end-to-end
- ✅ /health returns green for all services
- ✅ pytest passes

## Status: COMPLETE
