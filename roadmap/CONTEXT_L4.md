# CONTEXT_L4 — Deep FS Analysis

## What This Level Builds
Extends the pipeline with three more analysis capabilities:
contradiction detection, missing edge case identification,
and an overall FS quality score.

## Stack Used
LangGraph (adds 3 new nodes) · LLM client · PostgreSQL

## Build Order (5 prompts)

### Prompt 01 — Contradiction detection node
```
backend/app/pipeline/nodes/contradiction_node.py
  contradiction_node(state) -> state
  For each pair of sections: check for conflicting statements
  LLM prompt: "Do these two requirements contradict each other?
               If yes, explain the conflict and which section to trust."
  Returns List[Contradiction]:
    section_a_index, section_a_heading, section_b_index, section_b_heading,
    description, severity, suggested_resolution
```

### Prompt 02 — Edge case detection node
```
backend/app/pipeline/nodes/edge_case_node.py
  edge_case_node(state) -> state
  For each section: ask LLM what scenarios are not covered
  Focus on: error states, empty inputs, permission boundaries,
            concurrent operations, data validation boundaries
  Returns List[EdgeCaseGap]:
    section_index, section_heading, scenario_description, impact, suggested_addition
```

### Prompt 03 — FS quality scorer
```
backend/app/pipeline/nodes/quality_node.py
  quality_node(state) -> state
  Computes FSQualityScore:
    completeness: float   (% of sections with no gaps)
    clarity: float        (% of sections with no ambiguities)
    consistency: float    (1 - contradiction_rate)
    overall: float        (weighted average: 35% completeness + 35% clarity + 30% consistency)
  Updates state.quality_score
  Also: compliance_tags — flags sections mentioning payments,
        auth, PII, external APIs (for governance tagging)
```

### Prompt 04 — Update pipeline + API
```
Update LangGraph graph:
  ambiguity_node → contradiction_node → edge_case_node → quality_node → END

Update db/models.py:
  ContradictionDB, EdgeCaseGapDB, ComplianceTagDB tables

backend/app/api/analysis_router.py — added:
  GET /api/fs/{id}/contradictions
  PATCH /api/fs/{id}/contradictions/{contradiction_id}
  GET /api/fs/{id}/edge-cases
  PATCH /api/fs/{id}/edge-cases/{edge_case_id}
  GET /api/fs/{id}/quality-score (full dashboard)
```

### Prompt 05 — Frontend: quality dashboard
```
frontend/src/app/documents/[id]/quality/page.tsx
  Large quality score SVG gauge (0-100) with colour coding
  Three sub-scores: completeness, clarity, consistency (bar + percentage)
  Tabbed content: contradictions / edge cases / compliance
  Contradiction list with both conflicting sections side-by-side
  Edge case gaps list with impact badge + resolve button
  Compliance tags shown as coloured pills grouped by category
```

## Done When
- ✅ Pipeline runs all 4 analysis nodes in sequence
- ✅ Quality score appears in UI with breakdown
- ✅ Contradictions and edge case gaps visible
- ✅ All stored in PostgreSQL
- ✅ 27 new tests pass (66 total)

## Built
- Contradiction detection node (LLM-powered pairwise section comparison)
- Edge case detection node (LLM-powered scenario gap analysis)
- Quality scoring node (computed sub-scores + LLM-powered compliance tagging)
- Extended pipeline state: Contradiction, EdgeCaseGap, ComplianceTag, FSQualityScore models
- LangGraph pipeline: parse → ambiguity → contradiction → edge_case → quality → END
- 3 new DB tables: contradictions, edge_case_gaps, compliance_tags
- 6 new API endpoints: GET/PATCH contradictions, GET/PATCH edge-cases, GET quality-score
- Updated analyze endpoint to persist all L4 results
- Frontend quality dashboard with SVG gauge, sub-score bars, tabbed content
- Frontend API client extended with all L4 types and functions
- Document detail page links to quality dashboard
- 27 new tests (66 total): state models, score computation, all nodes, pipeline flow, API endpoints

## Status: ✅ COMPLETE
