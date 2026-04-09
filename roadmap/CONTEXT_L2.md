# CONTEXT_L2 — Document Parsing

## What This Level Builds
The ability to read any FS document (PDF, DOCX, plain text) and extract
clean, structured content that the AI pipeline can reason over.

## Stack Used
pypdf · python-docx · OpenAI Embeddings · PostgreSQL (updates FSDocument)

## Build Order (6 prompts)

### Prompt 01 — Install + configure parsers
```
Add to requirements.txt and install:
  pypdf, python-docx, openai

Create backend/app/parsers/base.py:
  ParsedFS dataclass:
    raw_text: str
    sections: List[FSSection]
    metadata: dict

  FSSection dataclass:
    heading: str
    content: str
    section_index: int

  FSChunk dataclass:
    section_heading: str
    text: str
    chunk_index: int
    embedding: Optional[List[float]]
```

### Prompt 02 — PDF parser
```
backend/app/parsers/pdf_parser.py
  parse_pdf(filepath: str) -> ParsedFS
  Uses pypdf for text extraction
  Heuristic heading detection (ALL CAPS, numbered patterns, etc.)
  Handle scanned PDFs gracefully (log warning, return raw text)
```

### Prompt 03 — DOCX parser
```
backend/app/parsers/docx_parser.py
  parse_docx(filepath: str) -> ParsedFS
  Use python-docx to extract headings + paragraphs
  Map Word heading styles to FSSection headings
  Preserve numbered lists as requirement candidates
```

### Prompt 04 — Parser router + PostgreSQL update
```
backend/app/parsers/router.py
  parse_document(fs_id: str, db: AsyncSession) -> ParsedFS
  Routes to correct parser based on filetype
  On success: updates FSDocument.parsed_text + status=PARSED in postgres
  On failure: updates status=ERROR, logs error

backend/app/parsers/txt_parser.py
  parse_txt(filepath: str) -> ParsedFS
  Simple line-based section detection

backend/app/api/fs_router.py — add:
  POST /api/fs/{id}/parse — triggers parsing for uploaded document
    Updates status: UPLOADED → PARSING → PARSED
```

### Prompt 05 — Chunking + embedding storage
```
backend/app/parsers/chunker.py
  chunk_parsed_fs(parsed: ParsedFS) -> List[FSChunk]
  FSChunk: section_heading, text, chunk_index, embedding (optional)
  Chunk by section boundaries — do NOT split mid-sentence
  Max ~800 tokens per chunk

backend/app/vector/fs_store.py
  store_fs_chunks(fs_id, chunks) -> int
  Embeds each chunk using EMBEDDING_MODEL via OpenAI
  Upserts into qdrant fs_requirements collection
  Payload: { fs_id, section_heading, chunk_index, text }
```

### Prompt 06 — QA + frontend status
```
POST /api/fs/{id}/parse returns structured ParsedFS as JSON
Sections visible in API response
frontend/src/app/documents/[id]/page.tsx:
  Shows document metadata + parsed sections list
  Status badge: UPLOADED / PARSING / PARSED / ERROR
  Expand/collapse all sections accordion
pytest tests/test_parser.py — test PDF, DOCX, TXT parsing + chunking + API
```

## Files Created/Modified in L2

```
backend/app/parsers/
  __init__.py         [NEW]
  base.py             [NEW] — FSSection, ParsedFS, FSChunk dataclasses
  pdf_parser.py       [NEW] — pypdf-based PDF parser
  docx_parser.py      [NEW] — python-docx-based DOCX parser
  txt_parser.py       [NEW] — plain-text parser
  router.py           [NEW] — parser dispatcher + DB status updates
  chunker.py          [NEW] — section-aware chunker

backend/app/vector/
  fs_store.py         [NEW] — OpenAI embedding + Qdrant upsert

backend/app/api/
  fs_router.py        [MODIFIED] — added POST /api/fs/{id}/parse endpoint

backend/app/models/
  schemas.py          [MODIFIED] — added FSSectionSchema, ParseResponse

backend/
  requirements.txt    [MODIFIED] — added pypdf, python-docx, openai

backend/tests/
  test_parser.py      [NEW] — 18 tests (unit + integration)

frontend/src/lib/
  api.ts              [MODIFIED] — added parseDocument(), FSSection type

frontend/src/app/documents/[id]/
  page.tsx            [MODIFIED] — parse button, sections accordion

frontend/src/app/
  globals.css         [MODIFIED] — added .parsed badge + pulse animation
```

## Done When
- ✅ Upload a real FS TXT → /parse → sections appear in API response
- ✅ Sections stored in Qdrant with embeddings (non-fatal if no API key)
- ✅ Frontend shows parsed sections for a document
- ✅ Status flow works: UPLOADED → PARSING → PARSED
- ✅ 26 total tests passing (18 L2 + 8 L1)

## Built
- ✅ Parser base dataclasses (FSSection, ParsedFS, FSChunk)
- ✅ PDF parser (pypdf with heuristic heading detection)
- ✅ DOCX parser (python-docx with heading style mapping)
- ✅ TXT parser (line-based heuristic section detection)
- ✅ Parser router (dispatches by extension, manages DB status flow)
- ✅ Section-aware chunker (sentence-boundary splitting, ~800 tokens/chunk)
- ✅ Vector store module (OpenAI embeddings + Qdrant upsert)
- ✅ POST /api/fs/{id}/parse API endpoint
- ✅ Frontend parse button + sections accordion (expand/collapse all)
- ✅ Status badges: UPLOADED (blue), PARSING (amber), PARSED (green), ERROR (red)
- ✅ 26 tests — all passing

## Status: COMPLETE
