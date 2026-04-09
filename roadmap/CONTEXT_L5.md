# CONTEXT_L5 — Task Decomposition

## What This Level Builds
The core output the developer actually uses. Takes the analysed FS
and produces a structured, sequential list of dev tasks with
dependencies, acceptance criteria, and effort complexity hints.

## Stack Used
LangGraph (adds 3 new nodes: task_decomposition, dependency, traceability) · LLM · PostgreSQL

## Build Order (6 prompts)

### Prompt 01 — FSTask model
```
backend/app/pipeline/state.py — added:
  FSTask: task_id, title, description, section_index, section_heading,
          depends_on, acceptance_criteria, effort, tags, order, can_parallel
  EffortLevel enum: LOW, MEDIUM, HIGH, UNKNOWN
  TraceabilityEntry: task_id, task_title, section_index, section_heading
  FSAnalysisState: added tasks, traceability_matrix fields

backend/app/db/models.py — added:
  EffortLevel enum
  FSTaskDB table (fs_tasks): task_id, title, description, section_index,
    section_heading, depends_on (JSON), acceptance_criteria (JSON), effort,
    tags (JSON), order, can_parallel
  TraceabilityEntryDB table (traceability_entries): task_id, task_title,
    section_index, section_heading
```

### Prompt 02 — Task decomposition node
```
backend/app/pipeline/nodes/task_node.py
  task_decomposition_node(state) → state
  For each FS section (skipping unresolved HIGH ambiguities):
    LLM: decompose into atomic dev tasks
    Each task: title, description, acceptance_criteria, effort, tags
  Returns state with tasks populated
```

### Prompt 03 — Dependency graph builder
```
backend/app/pipeline/nodes/dependency_node.py
  dependency_node(state) → state
  Takes state.tasks, uses LLM to infer inter-task dependencies
  Validates: no cycles (DFS cycle detection)
  Assigns execution order (Kahn's algorithm topological sort)
  Flags tasks that can be parallelised (same depth level)
```

### Prompt 04 — Traceability matrix
```
backend/app/pipeline/nodes/traceability_node.py
  traceability_node(state) → state
  Builds TraceabilityMatrix: maps each task → source section
  Stored as state.traceability_matrix
```

### Prompt 05 — API endpoints
```
backend/app/api/tasks_router.py:
  GET /api/fs/{id}/tasks — ordered task list
  GET /api/fs/{id}/tasks/{task_id} — single task detail
  PATCH /api/fs/{id}/tasks/{task_id} — update task (manual edit)
  GET /api/fs/{id}/tasks/dependency-graph — graph as adjacency list + edges
  GET /api/fs/{id}/traceability — full traceability matrix

backend/app/api/analysis_router.py — updated:
  Persists tasks and traceability to DB on analyze
  Clears existing L5 data on re-analysis
  Response includes tasks_count
```

### Prompt 06 — Frontend: task board
```
frontend/src/app/documents/[id]/tasks/page.tsx
  Ordered task list with expandable cards:
    - Title with execution order badge
    - Effort badge (color-coded: green/amber/red)
    - Tag pills with distinct colors
    - Source section reference
    - Parallel badge when applicable
    - Dependency count indicator
  Expanded view shows:
    - Full description
    - Acceptance criteria list
    - Dependency links with order numbers
  Dependency tree visualisation (grouped by depth level)
  Traceability matrix (tasks grouped by source section)
  "Export to JIRA" placeholder button (wired in L10)
  Summary stats: total, effort breakdown, deps, parallel count
```

## Done When
- ✅ Pipeline produces ordered task list from FS
- ✅ Each task links back to source FS section
- ✅ Dependencies visualised in UI
- ✅ Traceability matrix available via API
- ✅ All 95 tests pass (66 existing + 29 new)

## Built
- FSTask model (task_id, title, description, depends_on, acceptance_criteria, effort, tags, order, can_parallel)
- EffortLevel enum (LOW/MEDIUM/HIGH/UNKNOWN)
- TraceabilityEntry model
- Task decomposition node (LLM-powered, skips HIGH ambiguity sections)
- Dependency graph builder node (LLM inference + DFS cycle detection + Kahn's topological sort + parallel detection)
- Traceability matrix node
- Extended pipeline: 8 nodes (parse → ambiguity → contradiction → edge_case → quality → task_decomposition → dependency → traceability → END)
- 2 new DB tables: fs_tasks, traceability_entries
- 5 new API endpoints (GET/PATCH tasks, GET task detail, GET dependency-graph, GET traceability)
- Updated analyze endpoint to persist L5 data
- Frontend task board with expandable cards, dependency tree, traceability matrix
- Frontend API client extended with all L5 types and functions
- Document detail page links to task board
- 29 new tests (95 total): state models, dependency utilities, all nodes, pipeline flow, API endpoints

## Status: ✅ COMPLETE
