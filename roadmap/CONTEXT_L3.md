# CONTEXT_L3 — Ambiguity Detection

## What This Level Builds
The core AI feature. LangGraph pipeline that reads parsed FS sections
and flags vague, incomplete, or unclear requirements — with suggested
clarification questions for the functional team.

## Stack Used
LangGraph · OpenAI (gpt-4o-mini via LLM client) · PostgreSQL

## Key Design
LLM-powered ambiguity detection with structured JSON prompts. The detector
analyzes each section for vague language, missing quantification, undefined
references, incomplete logic, and conflicting statements. Each flag includes
severity (HIGH/MEDIUM/LOW), reason, and a clarification question for the
functional team.

## Build Order (7 prompts)

### Prompt 01 — LangGraph pipeline skeleton
```
backend/app/pipeline/state.py
  FSAnalysisState (TypedDict):
    fs_id, parsed_sections, ambiguities, contradictions, tasks,
    quality_score, errors

  AmbiguityFlag, Severity, SectionInput, Contradiction, FSTask pydantic models

backend/app/pipeline/graph.py
  Build LangGraph StateGraph
  Nodes: START → parse_node → ambiguity_node → END
```

### Prompt 02 — Ambiguity detector (LLM)
```
backend/app/pipeline/nodes/ambiguity_node.py
  detect_ambiguities_in_section(heading, content, index) -> List[AmbiguityFlag]
  Structured system prompt for ambiguity detection
  JSON response parsing with validation
  ambiguity_node(state) -> state — LangGraph node function
```

### Prompt 03 — DSPy optimization + benchmarking (Deferred)
```
DSPy integration deferred — direct LLM with structured prompts achieves
strong detection quality. The baseline (single structured LLM call) is
already implemented. DSPy BootstrapFewShot can be added post-L7 for
thesis comparison if needed, using the same prompt templates.
```

### Prompt 04 — LangGraph ambiguity node + state update
```
Integrated into graph.py:
  START → parse_node → ambiguity_node → END
  run_analysis_pipeline(fs_id, sections) entry point
```

### Prompt 05 — Persist ambiguities to PostgreSQL
```
db/models.py:
  AmbiguityFlagDB: id, fs_id, section_index, section_heading, flagged_text,
                   reason, severity, clarification_question, resolved, created_at
  AmbiguitySeverity enum (LOW/MEDIUM/HIGH)

api/analysis_router.py:
  POST /api/fs/{id}/analyze — runs pipeline, persists flags
  GET  /api/fs/{id}/ambiguities — list all flags
  PATCH /api/fs/{id}/ambiguities/{flag_id} — mark resolved
```

### Prompt 06 — Frontend: ambiguity review UI
```
frontend/src/app/documents/[id]/ambiguities/page.tsx
  Run Analysis / Re-analyze button
  Stats dashboard: total, high, medium, low, resolved counts
  Progress bar with resolution percentage
  Severity-coded flag cards with:
    - Flagged text (highlighted)
    - Reason explanation
    - Clarification question for functional team
    - "Mark Resolved" button per flag
```

### Prompt 07 — QA
```
pytest tests/test_ambiguity.py — 13 tests (unit + integration)
  State models, ambiguity node, pipeline graph, analysis API
All 39 tests passing (13 L3 + 18 L2 + 8 L1)
E2E verified via browser: Upload → Parse → Analyze → View/Resolve flags
```

## Files Created/Modified in L3

```
backend/app/pipeline/
  __init__.py           [NEW]
  state.py              [NEW] — FSAnalysisState, AmbiguityFlag, Severity
  graph.py              [NEW] — LangGraph StateGraph + run_analysis_pipeline
  nodes/
    __init__.py          [NEW]
    ambiguity_node.py    [NEW] — LLM ambiguity detection + node function

backend/app/api/
  analysis_router.py     [NEW] — POST analyze, GET ambiguities, PATCH resolve

backend/app/db/
  models.py              [MODIFIED] — added AmbiguityFlagDB, AmbiguitySeverity

backend/app/models/
  schemas.py             [MODIFIED] — added AmbiguityFlagSchema, AnalysisResponse

backend/app/llm/
  client.py              [MODIFIED] — added OpenAI support, call_llm_json()

backend/app/api/
  health_router.py       [MODIFIED] — provider-aware LLM health check

backend/
  main.py                [MODIFIED] — registered analysis_router
  requirements.txt       [MODIFIED] — added langgraph, langchain-core

backend/tests/
  test_ambiguity.py      [NEW] — 13 tests

frontend/src/lib/
  api.ts                 [MODIFIED] — AmbiguityFlag, AnalysisResponse, API functions

frontend/src/app/documents/[id]/
  page.tsx               [MODIFIED] — "View Ambiguity Analysis" link
  ambiguities/page.tsx   [NEW] — full ambiguity review UI
```

## Done When
- ✅ Upload FS → parse → analyze → ambiguities appear with severity + questions
- ✅ LLM (gpt-4o-mini) detects real ambiguities in FS sections
- ✅ Frontend shows review UI with resolve flow
- ✅ 39 total tests passing (13 L3 + 18 L2 + 8 L1)
- ✅ Status flow: PARSED → ANALYZING → COMPLETE
- ✅ Ambiguity flags persisted in PostgreSQL with resolve tracking

## Built
- ✅ LangGraph pipeline skeleton (FSAnalysisState, StateGraph)
- ✅ Ambiguity detection node (structured LLM prompts, JSON parsing)
- ✅ LangGraph integration (parse_node → ambiguity_node → END)
- ✅ AmbiguityFlagDB model with severity enum + resolved state
- ✅ Analysis API (analyze, list flags, resolve flag)
- ✅ Multi-provider LLM client (OpenAI + Anthropic with call_llm_json)
- ✅ Frontend ambiguity review page (stats, progress, flag cards, resolve)
- ✅ Provider-aware health check
- ✅ 13 new tests — all passing

## Status: COMPLETE
