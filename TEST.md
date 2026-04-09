You are a senior QA engineer. Your job is to write and execute a complete 
end-to-end test suite for the FS Intelligence Platform — a full-stack app 
with a FastAPI backend and Next.js frontend. All 10 levels must be tested.

=============================================================
REPO STRUCTURE (read before writing any tests)
=============================================================
- Backend: /backend — FastAPI, LangGraph pipeline, PostgreSQL, Qdrant
- Frontend: /frontend — Next.js 14 App Router + TypeScript
- Config: /.env for secrets, /docker-compose.yml for services
- Tests already exist in /backend/tests/ (172+ passing) — do NOT break them

=============================================================
STEP 0 — ENVIRONMENT SETUP VERIFICATION
=============================================================
Before writing any test, verify:
1. Read /docker-compose.yml — confirm postgres, qdrant, backend, frontend 
   services are all defined correctly
2. Read /backend/requirements.txt — confirm all packages present:
   fastapi, langchain, langgraph, dspy, crewai, qdrant-client, sqlalchemy,
   llama-index, unstructured, reportlab, python-docx, anthropic, openai
3. Read /backend/app/config.py — confirm all env vars are referenced
4. Read /frontend/package.json — confirm next, react, typescript present
5. Read /backend/app/api/ — list ALL router files and their prefixes
6. Read /backend/app/pipeline/ — list ALL LangGraph nodes

Fix any missing import, missing env var reference, or misconfigured 
docker-compose before proceeding.

=============================================================
STEP 1 — DOCKER + SERVICES HEALTH CHECK
=============================================================
Run: docker-compose up -d
Then verify all 4 services are healthy:
  curl http://localhost:8000/health  → { "status": "ok" }
  curl http://localhost:6333/       → Qdrant root responds
  psql $DATABASE_URL -c "\dt"       → tables exist
  curl http://localhost:3000        → Next.js 200 OK

If any service fails: read its Dockerfile, find the bug, fix it, rebuild.

=============================================================
STEP 2 — DATABASE SCHEMA VERIFICATION
=============================================================
Connect to PostgreSQL and confirm ALL these tables exist with correct columns:

Core: fs_documents, fs_sections, fs_chunks
L3:   ambiguity_flags
L4:   contradictions, edge_case_gaps, compliance_tags, quality_scores
L5:   fs_tasks, traceability_entries
L6:   debate_results
L7:   fs_versions, fs_changes, task_impacts, rework_estimates
L8:   code_uploads
L9:   duplicate_flags, fs_comments, fs_mentions, fs_approvals, audit_events
L10:  test_cases

For each table: run \d <table_name> and confirm columns match the Pydantic
models in /backend/app/models/. Fix any schema drift with Alembic migrations
or by running the table creation logic.

=============================================================
STEP 3 — BACKEND API ENDPOINT TEST (pytest + httpx)
=============================================================
Create /backend/tests/test_e2e_full.py

Use a REAL test FS document — create this fixture:

```python
TEST_FS_CONTENT = """
# Payment Gateway Integration

## 1. Overview
The system shall integrate with Stripe and PayPal payment processors.
Users can pay via credit card, debit card, or digital wallet.

## 2. Authentication
All API calls must be authenticated using OAuth 2.0.
The session timeout shall be 30 minutes.
The session timeout shall be 60 minutes.  # INTENTIONAL CONTRADICTION

## 3. Transaction Limits
Daily transaction limit is unspecified for premium users.  # INTENTIONAL AMBIGUITY
Standard users are limited to $10,000 per day.

## 4. Error Handling
On payment failure, the system should retry. The number of retries is TBD.
PII data including card numbers must be encrypted at rest.

## 5. Reporting
Admins can export transaction reports in CSV and PDF format.
Reports must be generated within an unspecified time frame.  # AMBIGUITY
"""
```

Write tests for EVERY endpoint in this exact order:

--- L1-L2: UPLOAD + PARSE ---
test_upload_document:
  POST /api/fs/upload with multipart file (write TEST_FS_CONTENT to a .txt)
  Assert: 201, response has { data: { id, filename, status } }
  Save document_id for all subsequent tests

test_parse_document:
  POST /api/fs/{document_id}/parse
  Assert: 200, sections list non-empty, each section has { title, content }
  Assert: Qdrant has vectors stored (GET /api/fs/{document_id}/sections)

--- L3: AMBIGUITY DETECTION ---
test_run_analysis:
  POST /api/fs/{document_id}/analyze
  Assert: 200, pipeline runs to completion
  Assert: response contains ambiguity_flags list
  Assert: at least 2 HIGH severity flags detected (premium users + reports)

test_list_ambiguities:
  GET /api/fs/{document_id}/ambiguities
  Assert: 200, flags non-empty, each has { id, description, severity, section }

test_resolve_ambiguity:
  PATCH /api/fs/{document_id}/ambiguities/{flag_id}/resolve
  body: { "resolution": "Premium users have a $50,000 daily limit" }
  Assert: 200, flag status = RESOLVED

--- L4: DEEP ANALYSIS ---
test_contradictions:
  GET /api/fs/{document_id}/contradictions
  Assert: at least 1 contradiction detected (30min vs 60min session timeout)
  Assert: each contradiction has { section_a, section_b, description }

test_edge_cases:
  GET /api/fs/{document_id}/edge-cases
  Assert: non-empty list, each has { description, severity }

test_quality_score:
  GET /api/fs/{document_id}/quality-score
  Assert: score between 0-100, sub-scores for completeness/clarity/consistency
  Assert: compliance_tags includes "payments" and "PII"

--- L5: TASK DECOMPOSITION ---
test_task_list:
  GET /api/fs/{document_id}/tasks
  Assert: non-empty, each task has { id, title, effort, tags, acceptance_criteria }
  Assert: at least one task tagged "auth" and one tagged "payments"

test_dependency_graph:
  GET /api/fs/{document_id}/dependency-graph
  Assert: { nodes: [...], edges: [...] } structure
  Assert: no circular dependencies (graph is a DAG)

test_traceability:
  GET /api/fs/{document_id}/traceability
  Assert: matrix entries link task IDs to section IDs

--- L6: ADVERSARIAL DEBATE ---
test_debate_results:
  GET /api/fs/{document_id}/debate-results
  Assert: results exist for HIGH severity flags
  Assert: each result has { red_argument, blue_argument, arbiter_verdict, confidence }
  Assert: at least one verdict is CLEAR or AMBIGUOUS

--- L7: CHANGE IMPACT ANALYSIS ---
test_upload_new_version:
  Create UPDATED_FS_CONTENT = TEST_FS_CONTENT + new section on "Refunds"
  + modify session timeout from 30 to 45 minutes
  POST /api/fs/{document_id}/versions with new file
  Assert: 201, version_id returned

test_version_diff:
  GET /api/fs/{document_id}/diff?v1={v1_id}&v2={v2_id}
  Assert: changed sections detected, diff has { added, removed, modified } keys

test_impact_analysis:
  GET /api/fs/{document_id}/impact?version_id={v2_id}
  Assert: task_impacts list non-empty
  Assert: auth-related tasks show REQUIRES_REVIEW status

test_rework_estimate:
  GET /api/fs/{document_id}/rework?version_id={v2_id}
  Assert: { total_days, breakdown: [...] } structure
  Assert: total_days > 0

--- L8: LEGACY CODE REVERSE FS ---
test_code_upload:
  Create a minimal Python zip archive with:
    - auth_service.py (JWT login/logout functions)
    - payment_service.py (charge, refund functions)
    - models.py (User, Transaction dataclasses)
  POST /api/code/upload with the zip file
  Assert: 201, code_upload_id returned

test_generate_reverse_fs:
  POST /api/code/{code_upload_id}/generate-fs
  Assert: 200, generated_fs has sections
  Assert: sections mention authentication and payments

test_reverse_fs_quality:
  GET /api/code/{code_upload_id}/report
  Assert: { coverage_score, confidence_score, gaps: [...] } structure

--- L9: SEMANTIC INTELLIGENCE + COLLABORATION ---
test_duplicate_detection:
  Upload a second FS document with content overlapping TEST_FS_CONTENT
  POST /api/fs/{doc2_id}/analyze
  GET /api/fs/{doc2_id}/duplicates
  Assert: duplicate flags exist with similarity > 0.88

test_requirement_library:
  GET /api/library/search?query=authentication
  Assert: returns matching items from approved FS documents

test_comment_thread:
  POST /api/fs/{document_id}/comments
  body: { section_id, content: "This section needs @alice to clarify limits" }
  Assert: 201, mention for "alice" extracted

  GET /api/fs/{document_id}/comments
  Assert: comment visible with mention

test_approval_workflow:
  POST /api/fs/{document_id}/approval/submit
  Assert: status = PENDING

  POST /api/fs/{document_id}/approval/approve
  Assert: status = APPROVED
  Assert: audit trail has APPROVAL_GRANTED event

test_audit_trail:
  GET /api/fs/{document_id}/audit
  Assert: events include DOCUMENT_UPLOADED, DOCUMENT_ANALYZED, APPROVAL_GRANTED
  Assert: events have { event_type, timestamp, metadata } structure

--- L10: INTEGRATIONS + EXPORT ---
test_jira_export:
  POST /api/export/{document_id}/jira
  Assert: 200, response has { epics_created, stories_created } (simulated mode OK)

test_confluence_export:
  POST /api/export/{document_id}/confluence
  Assert: 200, response has { page_url } or simulated confirmation

test_test_cases:
  GET /api/fs/{document_id}/test-cases
  Assert: non-empty, each has { title, type, steps, expected_result }
  Assert: TestType values are valid enum entries

test_pdf_export:
  GET /api/export/{document_id}/pdf
  Assert: 200, Content-Type = application/pdf, body non-empty (> 1KB)

test_word_export:
  GET /api/export/{document_id}/word
  Assert: 200, Content-Type = application/vnd.openxmlformats...
  Assert: body non-empty

test_csv_test_cases:
  GET /api/export/{document_id}/test-cases/csv
  Assert: 200, Content-Type = text/csv
  Assert: CSV has header row with Title, Type, Steps, Expected Result

=============================================================
STEP 4 — LANGGRAPH PIPELINE INTEGRITY
=============================================================
Read /backend/app/pipeline/ and verify:

1. Node count: pipeline must have exactly 11 nodes:
   parse_node → ambiguity_node → debate_node → contradiction_node → 
   edge_case_node → quality_node → task_decomposition_node → 
   dependency_node → traceability_node → duplicate_node → testcase_node → END

2. State model: open the state Pydantic model, confirm it contains fields for 
   ALL nodes' outputs (sections, ambiguity_flags, debate_results, 
   contradictions, edge_cases, quality_score, tasks, dependency_graph, 
   traceability, duplicate_flags, test_cases)

3. Async: confirm every node function is declared `async def`

4. Error handling: confirm every LLM call is inside try/except with fallback

5. Impact pipeline: confirm separate LangGraph graph exists in 
   /backend/app/pipeline/ with 3 nodes: version_node → impact_node → rework_node

6. Reverse pipeline: confirm separate LangGraph graph with: 
   reverse_fs_node → reverse_quality_node

If any node is missing, incorrectly connected, or not async — FIX IT.

=============================================================
STEP 5 — LLM CLIENT INTEGRITY
=============================================================
Read /backend/app/llm/client.py and verify:

1. Both providers supported: LLM_PROVIDER=anthropic uses claude-sonnet-4-20250514,
   LLM_PROVIDER=openai falls back cleanly
2. Model string is exactly "claude-sonnet-4-20250514" — not claude-3, not claude-2
3. All calls go through this single client — grep for any direct 
   anthropic.Anthropic() or openai.OpenAI() calls outside this file and remove them
4. Streaming and non-streaming both handled
5. Write test: call client with "Say hello" and assert non-empty string response

=============================================================
STEP 6 — FRONTEND VERIFICATION (Playwright or manual checklist)
=============================================================
Install playwright: cd frontend && npx playwright install

Create /frontend/tests/e2e.spec.ts

Test these flows:

test('upload flow'):
  Navigate to http://localhost:3000
  Find file upload input, upload a .txt FS file
  Assert: document appears in document list with status badge

test('analysis trigger and ambiguity review'):
  Click "Analyze" on the uploaded document
  Wait for analysis to complete (poll or wait for badge change)
  Navigate to /ambiguities/{document_id}
  Assert: severity stats visible (HIGH/MEDIUM/LOW counts)
  Assert: progress bar rendered
  Click "Resolve" on one flag, submit resolution
  Assert: flag marked as resolved

test('quality dashboard'):
  Navigate to /quality/{document_id}
  Assert: SVG gauge element rendered (svg circle or path)
  Assert: sub-score bars visible for completeness, clarity, consistency
  Assert: compliance tags visible (payments, PII)

test('task board'):
  Navigate to /tasks/{document_id}
  Assert: task cards rendered
  Click one card to expand
  Assert: acceptance criteria and effort visible
  Assert: dependency tree link clickable

test('impact dashboard — L7'):
  Navigate to /impact/{document_id}
  Assert: version upload input visible
  Upload a modified FS file
  Assert: rework summary card shows 4 metric tiles
  Assert: diff view renders side-by-side sections

test('library search — L9'):
  Navigate to /library
  Type "authentication" in search
  Assert: results appear with similarity scores

test('collaboration page — L9'):
  Navigate to /collaborate/{document_id}
  Assert: comment thread visible
  Assert: approval workflow buttons present (Submit / Approve / Reject)
  Assert: audit timeline rendered

test('traceability matrix — L10'):
  Navigate to /traceability/{document_id}
  Assert: grid renders sections × tasks
  Assert: orphaned task warnings and uncovered section warnings visible

=============================================================
STEP 7 — DSPY AMBIGUITY MODULE CHECK
=============================================================
Read /backend/app/pipeline/ambiguity_node.py (or wherever DSPy is used):

1. Confirm DSPy Signature is defined (not raw f-string prompts)
2. Confirm DSPy Module compiled or using Predict/ChainOfThought correctly
3. Confirm the module is called inside the LangGraph node, not standalone
4. Write a unit test: instantiate the DSPy module, pass in a section with 
   the word "unspecified", assert at least one flag returned with 
   severity HIGH or MEDIUM

=============================================================
STEP 8 — CREWAI DEBATE SYSTEM CHECK
=============================================================
Read /backend/app/agents/ and verify:

1. RedAgent and BlueAgent both defined as CrewAI Agent objects
2. ArbiterAgent defined
3. Crew assembled with all 3 agents and correct task definitions
4. Debate only triggers for HIGH severity flags (check conditional logic)
5. CLEAR verdicts correctly filter flags from final ambiguity list
6. Write unit test: mock one HIGH severity flag, run debate,
   assert result has { verdict, confidence, reasoning }
   assert verdict is either "CLEAR" or "AMBIGUOUS"

=============================================================
STEP 9 — QDRANT VECTOR STORE CHECK
=============================================================
Read /backend/app/vector/ and verify:

1. Collection created on startup if not exists
2. Upsert uses correct payload structure: { doc_id, section_id, text }
3. Similarity search returns top-k with score threshold
4. 3 functions exist: search_similar_sections, store_library_item, search_library
5. Write test: upsert 3 fake sections, search for one, assert correct hit returned

=============================================================
STEP 10 — RUN COMPLETE TEST SUITE
=============================================================
Run all tests:
  cd backend && pytest tests/ -v --tb=short 2>&1 | tee test_results.txt

Pass threshold: ALL tests must pass. 0 failures allowed.

If any test fails:
1. Read the full traceback
2. Find the root cause (missing import, wrong DB column, wrong endpoint path, 
   LangGraph node not connected, Pydantic field missing)
3. Fix the source file — not the test
4. Re-run only the failed test
5. Repeat until green

After backend passes:
  cd frontend && npx playwright test --reporter=list 2>&1 | tee frontend_results.txt

All Playwright tests must pass.

=============================================================
STEP 11 — FINAL REPORT
=============================================================
After all tests pass, output a report in this format:

## FS Platform — E2E Test Report

| Level | Feature | Backend Tests | Frontend Tests | Status |
|-------|---------|--------------|----------------|--------|
| L1    | Upload + health | pass (N) | upload flow ✓ | ✅ |
| L2    | Parse + vectors | pass (N) | sections accordion ✓ | ✅ |
| L3    | Ambiguity detect | pass (N) | review page ✓ | ✅ |
| L4    | Deep analysis | pass (N) | quality dashboard ✓ | ✅ |
| L5    | Task decomp | pass (N) | task board ✓ | ✅ |
| L6    | Debate system | pass (N) | debate transcript ✓ | ✅ |
| L7    | Change impact | pass (N) | impact dashboard ✓ | ✅ |
| L8    | Reverse FS | pass (N) | reverse dashboard ✓ | ✅ |
| L9    | Semantic + collab | pass (N) | library + collab ✓ | ✅ |
| L10   | Integrations | pass (N) | traceability matrix ✓ | ✅ |

Total backend tests: N passing, 0 failing
Total frontend tests: N passing, 0 failing
Pipeline nodes verified: 11/11
LLM client: anthropic/claude-sonnet-4-20250514 confirmed
Qdrant collections: confirmed
PostgreSQL tables: 20+ confirmed

If anything is NOT ✅, do not produce this report — fix it first.