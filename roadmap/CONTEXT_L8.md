# CONTEXT_L8 — Legacy Code → FS Reverse Generation ★

## What This Level Builds
The reverse direction. Upload an existing codebase (zip or folder),
and the tool generates a human-readable FS document from it.
Makes the product bidirectional — works for new projects AND
understanding old systems.

## Stack Used
LlamaIndex (code reader) · LangGraph · LLM · PostgreSQL

## Build Order (5 prompts)

### Prompt 01 — Code ingestion
```
backend/app/parsers/code_parser.py
  parse_codebase(zip_path: str) -> CodebaseSnapshot
    Extracts zip, reads .py .js .ts .java .go files
    For each file: extracts functions, classes, docstrings, comments
    Builds CodebaseSnapshot:
      files: List[CodeFile]
      language: str
      estimated_size: int (lines of code)
  Use LlamaIndex CodeSplitter for intelligent chunking
  Skip: node_modules, __pycache__, .git, build folders

POST /api/code/upload — upload zip of codebase
```

### Prompt 02 — FS generation pipeline
```
backend/app/pipeline/nodes/reverse_fs_node.py
  reverse_fs_node(state) -> state
  Multi-step LLM process:
    Step 1: "What does this module/class do?" per file
    Step 2: "What are the main user flows in this codebase?"
    Step 3: "Write an FS section for each identified flow"
    Step 4: Assemble into structured FSDocument format
  Output: GeneratedFS (same ParsedFS structure as normal FS)
  Store as FSDocument in postgres with source=GENERATED_FROM_CODE
```

### Prompt 03 — Quality check + gaps
```
backend/app/pipeline/nodes/reverse_quality_node.py
  After generating FS from code:
    Flag: sections where code logic is unclear (likely undocumented)
    Flag: functions with no docstrings (knowledge gap)
    Flag: sections that seem inconsistent with the code
  GeneratedFSReport:
    coverage: float (% of codebase documented)
    gaps: List[str] (undocumented areas)
    confidence: float (overall confidence in generated FS)
```

### Prompt 04 — API + storage
```
backend/app/api/code_router.py:
  POST /api/code/upload — accepts zip file
  POST /api/code/{id}/generate-fs — triggers reverse generation
  GET /api/code/{id}/generated-fs — returns generated FS document
  GET /api/code/{id}/report — coverage + gaps report
Generated FS can then be fed into normal forward pipeline (L3-L7)
```

### Prompt 05 — Frontend
```
frontend/src/app/reverse/page.tsx
  Upload zip of codebase
  Progress: Parsing code → Analysing modules → Generating FS → Done
  Generated FS viewer: sections + coverage percentage
  "Run full analysis on this FS" button → takes to normal pipeline
  Gaps highlighted in red with "low confidence" badge
```

## Done When
- Upload a real codebase zip → FS document generated ✅
- Coverage and gaps visible ✅
- Generated FS can be fed into the normal pipeline (L3-L7) ✅

## Status: ✅ COMPLETE

## Implementation Notes

### Pipeline State (state.py)
- Added Pydantic models: `CodeEntity`, `CodeFile`, `CodebaseSnapshot`, `GeneratedFSReport`
- Added `ReverseGenState` TypedDict for the reverse generation pipeline

### DB Models (models.py)
- Added `CodeUploadStatus` enum (UPLOADED/PARSING/PARSED/GENERATING/GENERATED/ERROR)
- Added `CodeUploadDB` table with snapshot, generated FS reference, and quality report fields

### Code Parser (parsers/code_parser.py)
- Python AST extraction (functions, classes, methods with docstrings/signatures)
- Regex-based extraction for JS/TS/Java/Go
- JSDoc comment extraction for JavaScript
- File filtering (skip node_modules, __pycache__, .git, build, venv, etc.)
- Zip extraction with single-folder wrapper detection
- Max file size limit (500KB)

### Pipeline Nodes
- `reverse_fs_node.py`: 4-step LLM process (module summaries → user flows → FS sections → assembly)
- `reverse_quality_node.py`: Deterministic coverage/confidence scoring with gap identification

### Pipeline Graph (graph.py)
- Separate `build_reverse_graph()`: START → reverse_fs_node → reverse_quality_node → END
- `run_reverse_pipeline()` entry point with independent singleton

### API Endpoints (code_router.py)
- `POST /api/code/upload` — upload zip + auto-parse
- `POST /api/code/{id}/generate-fs` — trigger reverse generation pipeline
- `GET /api/code/{id}/generated-fs` — get generated FS with sections and report
- `GET /api/code/{id}/report` — coverage + gaps report
- `GET /api/code/uploads` — list all uploads
- `GET /api/code/{id}` — upload detail

### Frontend (reverse/page.tsx)
- Zip upload with auto-parse
- Codebase list with status badges
- Generate FS button with progress indication
- Quality report card (coverage, confidence, gaps, section count)
- Gaps list with "LOW CONF" badges
- "Analyze Generated FS" link to forward pipeline
- Expandable generated FS sections viewer

### API Schemas (schemas.py)
- 8 new schemas: CodeUploadResponse, CodeEntitySchema, CodeFileSchema, CodeSnapshotSchema, CodeReportSchema, GeneratedFSResponse, CodeUploadDetailResponse, CodeUploadListResponse

### Tests (test_reverse.py)
- 65 tests, all passing
- Models, code parser (AST + regex + filtering + zip), quality node, pipeline graph, API endpoints, assembly
