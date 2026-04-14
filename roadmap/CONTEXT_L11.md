# CONTEXT_L11 -- Refinement, Accept/Resolve Flow, Build Engine, and MCP Server

## What This Level Builds
Post-L10 enhancements that complete the platform's professional-grade analysis
loop: AI-powered document refinement, accept/resolve workflow for all issue types
with bulk actions, cross-page sync, autonomous build engine with MCP tooling,
and real-time monitoring.

## Stack Used
LangGraph (refinement pipeline) . CrewAI . MCP SDK . FastAPI . Next.js . Qdrant

## Features Delivered

### 1. FS Refinement Pipeline
```
backend/app/pipeline/refinement_graph.py
  4-stage pipeline (not LangGraph graph, sequential calls):
    issues_collector_node  -- load unresolved ambiguities, contradictions, edge cases
    suggestion_node        -- LLM generates JSON fix suggestions per issue
    rewriter_node          -- full-doc LLM rewrite (mode=full)
    targeted_rewriter_node -- fuzzy paragraph replace (mode=targeted, <=5 issues)
    validation_node        -- score comparison, accept/reject vs baseline

  POST /api/fs/{id}/refine       -- preview with before/after scores + diff
  POST /api/fs/{id}/refine/accept -- persist refined text as new FSVersion

  Frontend: /documents/[id]/refine
    Side-by-side original vs refined panels
    Quality gauge comparison (before/after)
    Diff lines with add/remove highlighting
    Accept & Save / Reject actions
    Version history with view/revert
```

### 2. Accept Suggestion Flow (Edge Cases + Contradictions)
```
backend/app/api/analysis_router.py
  POST /{id}/edge-cases/{eid}/accept
    Merge suggested_addition into parsed_text at target section
    Create new FSVersion via _persist_refined_version
    Mark resolved = True
    Quality score updates live (completeness increases)

  POST /{id}/contradictions/{cid}/accept
    Merge suggested_resolution into parsed_text at section A
    Create new FSVersion
    Mark resolved = True
    Quality score updates live (consistency increases)

  Shared helper: _append_to_section(text, section_index, addition)
    Uses section_extractor to find insertion point
    Appends text at end of target section

  Frontend: quality/page.tsx
    "Accept suggestion" button for edge cases with suggested_addition
    "Accept resolution" button for contradictions with suggested_resolution
    Both next to existing "Mark resolved" button
    Dashboard refetches after every mutation
```

### 3. Bulk Actions
```
backend/app/api/analysis_router.py
  POST /{id}/edge-cases/bulk-accept    -- accept all unresolved with suggestions
  POST /{id}/edge-cases/bulk-resolve   -- mark all unresolved as resolved
  POST /{id}/contradictions/bulk-accept  -- accept all with resolutions
  POST /{id}/contradictions/bulk-resolve -- mark all resolved
  POST /{id}/ambiguities/bulk-resolve    -- mark all resolved

  Bulk-accept endpoints: iterate items, merge each into text, create ONE version

  Frontend: quality/page.tsx
    Bulk action bar above contradictions list: "Accept All Resolutions" + "Mark All Resolved"
    Bulk action bar above edge cases list: "Accept All Suggestions" + "Mark All Resolved"

  Frontend: ambiguities/page.tsx
    "Resolve All (N)" button in header with unresolved count
```

### 4. Cross-Page Sync
```
frontend/src/app/documents/[id]/page.tsx
  Ambiguity count shows UNRESOLVED only (filter a => !a.resolved)
  visibilitychange listener refetches analysis summary when tab visible
  Quality sub-scores auto-refresh from getQualityDashboard

frontend/src/app/documents/[id]/refine/page.tsx
  Post-accept redirects to /documents/{id}?autoAnalyze=1
  Detail page detects query param, auto-triggers analyzeDocument
  Removes param via router.replace to prevent re-trigger
```

### 5. Analysis Progress Auto-Hide
```
frontend/src/components/AnalysisProgress.tsx
  Detects isAnalyzing transition false -> clears progress after 1.5s
  Detects all nodes complete -> clears progress after 2s
  Title changes to "Analysis Complete" during hide phase
  Component unmounts cleanly after cleanup
```

### 6. Build Engine
```
backend/app/db/models.py
  BuildStateDB     -- phase, task index, completed/failed IDs, stack, output folder
  FileRegistryDB   -- files mapped to tasks/sections
  BuildSnapshotDB  -- rollback snapshots of registry + task states
  PipelineCacheDB  -- cached node results (input_hash -> result_data)

backend/app/api/build_router.py (15 endpoints)
  Build state CRUD, file registry CRUD, task context/verify
  place-requirement, pre-build-check, post-build-check
  snapshots + rollback, pipeline-cache management
  build-prompt generation

mcp-server/tools/build.py (14 MCP tools)
  Full build lifecycle: state management, file tracking, gates, snapshots
  check_library_for_reuse for cross-project knowledge transfer
```

### 7. MCP Server
```
mcp-server/
  server.py        -- MCP entrypoint, registers all tools/resources/prompts
  tools/           -- 8 modules: documents, analysis, tasks, build, impact,
                      collaboration, exports, reverse
  resources/       -- fs_document (full doc context), task_board
  prompts/         -- autonomous_build_from_fs, start_build_loop

  20+ tools wrapping FastAPI backend
  Real-time monitoring via MCPSessionDB + MCPSessionEventDB
  Frontend: /monitoring with activity log + build session tracker
```

### 8. Quality Score Fixes
```
backend/app/pipeline/nodes/quality_node.py
  Filter section_index to valid range before counting affected sections
  Clamp all sub-scores to [0, 100]

backend/app/api/analysis_router.py, build_router.py
  Standardized section counting to use extract_sections_from_text
  (was chunk_text_into_sections which gave different count)
```

### 9. Section Content Cleanup
```
frontend/src/app/documents/[id]/page.tsx
  Strip separator lines (---, ===, ~~~) from display
  Strip [REFINED] tags from display
  renderRichContent and contentPreview both apply cleanup
```

### 10. Version History and Revert
```
backend/app/api/impact_router.py
  GET /{id}/versions/{vid}/text  -- retrieve version body
  POST /{id}/versions/{vid}/revert -- restore document to version

frontend/src/app/documents/[id]/refine/page.tsx
  Collapsible version history section
  View button shows version text inline
  Revert button restores document to that version
```

## Status
All features complete and verified. Quality scores are accurate.
Cross-page sync confirmed working. Bulk actions tested end-to-end.

## Files Modified/Created
- `backend/app/api/analysis_router.py` -- accept/bulk endpoints, refinement
- `backend/app/api/build_router.py` -- 15 build endpoints
- `backend/app/api/impact_router.py` -- version text + revert
- `backend/app/pipeline/refinement_graph.py` -- refinement pipeline
- `backend/app/pipeline/nodes/quality_node.py` -- score fixes
- `backend/app/db/models.py` -- 4 new tables
- `frontend/src/lib/api.ts` -- 15+ new API functions
- `frontend/src/app/documents/[id]/quality/page.tsx` -- accept + bulk UI
- `frontend/src/app/documents/[id]/ambiguities/page.tsx` -- bulk resolve
- `frontend/src/app/documents/[id]/refine/page.tsx` -- refinement UI + versions
- `frontend/src/app/documents/[id]/page.tsx` -- cross-page sync + auto-analyze
- `frontend/src/app/monitoring/page.tsx` -- MCP monitoring dashboard
- `frontend/src/components/AnalysisProgress.tsx` -- auto-hide
- `mcp-server/` -- entire MCP server (new)
