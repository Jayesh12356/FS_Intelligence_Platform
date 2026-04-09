# CONTEXT_L10 — Integrations + Polish

## What This Level Builds
The final output layer. Export to JIRA/Confluence, full test case
generation, traceability matrix UI, and complete frontend polish.

## Stack Used
JIRA API · Confluence API · LLM (test cases) · React

## Build Order (6 prompts)

### Prompt 01 — JIRA export
```
backend/app/integrations/jira.py
  JiraClient:
    create_epic(fs_title) -> epic_id
    create_story(task: FSTask, epic_id) -> story_id
  POST /api/fs/{id}/export/jira:
    Creates one JIRA epic for the FS
    Creates one JIRA story per FSTask with:
      title, description, acceptance criteria as checklist
    Returns: { epic_url, story_urls }
Config: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN in settings
```

### Prompt 02 — Confluence export
```
backend/app/integrations/confluence.py
  ConfluenceClient:
    create_page(space_key, title, content) -> page_url
  POST /api/fs/{id}/export/confluence:
    Creates Confluence page with:
      FS sections, quality score, ambiguity summary,
      task breakdown table, traceability matrix
    Returns: { page_url }
Config: CONFLUENCE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN
```

### Prompt 03 — Test case generation
```
backend/app/pipeline/nodes/testcase_node.py
  testcase_node(state) -> state
  For each FSTask:
    LLM: "Generate test cases for this acceptance criterion"
    Returns List[TestCase]:
      title, preconditions, steps, expected_result, test_type (unit/integration/e2e)
  GET /api/fs/{id}/test-cases — all generated test cases
  Export as CSV or markdown table
```

### Prompt 04 — Traceability matrix UI
```
frontend/src/app/documents/[id]/traceability/page.tsx
  Table: rows = FS Sections, cols = Tasks, cells = linked/not-linked
  Highlight orphaned tasks (no source section)
  Highlight uncovered sections (no tasks generated)
  Export as PDF button
```

### Prompt 05 — PDF/Word report export
```
backend/app/api/export_router.py:
  GET /api/fs/{id}/export/pdf — full intelligence report as PDF
    Includes: quality score, ambiguities, tasks, traceability, test cases
  GET /api/fs/{id}/export/docx — same as Word doc
Use: reportlab (PDF) or python-docx (Word)
```

### Prompt 06 — Full UI polish + final QA
```
Dashboard page (/) — shows all documents with status + quality score
Document detail page — tabs: Overview | Analysis | Tasks | Impact | Audit
Global search bar — semantic search across all FS documents (Qdrant)
Loading states, error states, empty states on all pages
Final: pytest all tests pass, zero TypeScript errors
Demo walkthrough: upload FS → full analysis → tasks → JIRA export
```

## Done When
- ✅ Tasks export to JIRA with correct hierarchy
- ✅ Full report exports as PDF and Word
- ✅ Traceability matrix renders in UI
- ✅ Test cases generated and exportable
- ✅ Complete demo flow works end-to-end
- ✅ All tests pass
- ✅ 49 L10 tests pass, 329 total (0 regressions)

## Status: COMPLETE

### Implementation Summary
- **Config**: JIRA_URL/EMAIL/API_TOKEN/PROJECT_KEY + CONFLUENCE_URL/EMAIL/API_TOKEN/SPACE_KEY
- **Integrations**: JiraClient (create_epic, create_story, export_fs_tasks) + ConfluenceClient (create_page, create_fs_page, _build_page_content)
- **Pipeline**: testcase_node added as 11th node (after duplicate_node → END), LLM-powered with deterministic fallback
- **DB**: TestCaseDB table + TestType enum (UNIT/INTEGRATION/E2E/ACCEPTANCE)
- **Schemas**: 5 new Pydantic schemas (TestCaseSchema, TestCaseListResponse, JiraExportResponse, ConfluenceExportResponse, ReportExportResponse)
- **API**: export_router with 10 endpoints (JIRA export, Confluence export, test-cases list/CSV, PDF meta/download, DOCX meta/download)
- **Analysis**: analysis_router updated to persist test cases + include in cleanup
- **Frontend**: Enhanced dashboard (status cards, recent docs grid), traceability matrix page (sections×tasks grid, orphaned/uncovered highlights), document detail page with traceability link
- **Reports**: PDF via reportlab with styled tables + text fallback, DOCX via python-docx with structured tables + text fallback
