# CONTEXT_L7 — FS Change Impact Analysis ★

## What This Level Builds
The must-have differentiator. When the functional team updates an FS
mid-development, the tool automatically identifies which tasks are
now invalidated, what needs to be redone, and estimates rework cost.

## Stack Used
LangGraph · LLM · PostgreSQL (FSVersion table from L1)

## Build Order (6 prompts)

### Prompt 01 — FS versioning system
```
backend/app/api/fs_router.py — add:
  POST /api/fs/{id}/version — upload a new version of an existing FS
    Stores as new FSVersion row
    Runs parser on new version
    Triggers diff computation

backend/app/pipeline/nodes/version_node.py
  version_node: computes text diff between v_old and v_new
  Returns: List[FSChange]
    change_type: ADDED | MODIFIED | DELETED
    section_id: str
    old_text: str | None
    new_text: str | None
```

### Prompt 02 — Impact analyser
```
backend/app/pipeline/nodes/impact_node.py
  impact_node(state) -> state
  For each FSChange:
    LLM: "Given this requirement changed from X to Y,
          which of these dev tasks are now invalidated or affected?"
    Input: FSChange + current task list
    Returns: List[TaskImpact]
      task_id, impact_type: INVALIDATED | REQUIRES_REVIEW | UNAFFECTED,
      reason: str
```

### Prompt 03 — Rework cost estimator
```
backend/app/pipeline/nodes/rework_node.py
  rework_node(state) -> state
  For invalidated/review tasks:
    effort_map: LOW=0.5d, MEDIUM=2d, HIGH=5d, UNKNOWN=2d
    Compute: total_rework_days = sum(effort for invalidated tasks)
    ReworkEstimate:
      invalidated_count, review_count, total_rework_days,
      affected_sections, changes_summary
```

### Prompt 04 — Impact API endpoints
```
backend/app/api/impact_router.py:
  GET /api/fs/{id}/versions — list all versions
  GET /api/fs/{id}/versions/{v}/diff — diff between versions
  GET /api/fs/{id}/impact/{version_id} — full impact analysis
  GET /api/fs/{id}/impact/{version_id}/rework — rework estimate
```

### Prompt 05 — Frontend: change impact dashboard
```
frontend/src/app/documents/[id]/impact/page.tsx
  Version selector (dropdown: v1, v2, v3...)
  "What changed?" section: diff view, old vs new side-by-side
  Affected tasks list: INVALIDATED (red) | NEEDS REVIEW (amber) | OK (green)
  Rework summary card:
    X tasks invalidated · Y tasks need review · Est. Z days rework
```

### Prompt 06 — QA
```
Upload FS v1 → run analysis → get tasks
Upload FS v2 (with 2 changed sections)
Impact analysis shows correct invalidated tasks
Rework estimate is reasonable
pytest tests/test_impact.py
```

## Done When
- Upload a revised FS → impact analysis runs automatically ✅
- Invalidated tasks highlighted in UI ✅
- Rework estimate visible ✅
- Version history browsable ✅

## Status: ✅ COMPLETE

## Implementation Notes

### Pipeline State (state.py)
- Added enums: `ChangeType` (ADDED/MODIFIED/DELETED), `ImpactType` (INVALIDATED/REQUIRES_REVIEW/UNAFFECTED)
- Added Pydantic models: `FSChange`, `TaskImpact`, `ReworkEstimate`
- Added `FSImpactState` TypedDict for the impact pipeline

### DB Models (models.py)
- Extended `FSVersion` with `parsed_text`, `file_path`, `file_size`, `content_type` columns
- Added 3 new tables: `FSChangeDB`, `TaskImpactDB`, `ReworkEstimateDB`
- Added L7 relationships to `FSDocument` and `FSVersion`

### Pipeline Nodes
- `version_node.py`: Difflib-based section diff (heading-matched, 95% similarity threshold)
- `impact_node.py`: LLM-powered impact analysis with worst-case aggregation
- `rework_node.py`: Deterministic cost estimation (effort_map: LOW=0.5d, MEDIUM=2d, HIGH=5d, UNKNOWN=2d)

### Pipeline Graph (graph.py)
- Separate `build_impact_graph()`: START → version_node → impact_node → rework_node → END
- `run_impact_pipeline()` entry point with independent singleton

### API Endpoints (impact_router.py)
- `POST /api/fs/{id}/version` — upload + parse + auto-trigger impact pipeline
- `GET /api/fs/{id}/versions` — list all versions
- `GET /api/fs/{id}/versions/{v}/diff` — section-level diff
- `GET /api/fs/{id}/impact/{version_id}` — full impact analysis
- `GET /api/fs/{id}/impact/{version_id}/rework` — rework estimate

### Frontend (impact/page.tsx)
- Version upload & selector
- Rework summary card with 4 metric tiles
- Expandable diff view (side-by-side for MODIFIED, inline for ADDED/DELETED)
- Color-coded task impact list (sorted by severity)
- "Impact Analysis" link on document detail page

### Tests (test_impact.py)
- 52 tests, all passing
- Models, nodes, pipeline graph, API endpoints, chunk helper
