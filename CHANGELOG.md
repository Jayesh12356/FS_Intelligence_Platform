# Changelog

All notable changes to the FS Intelligence Platform are documented here. The
project follows semantic versioning.

## 0.2.0 — Platform Hardening

This release focuses on reliability, security, performance, and developer
experience. 35 discrete hardening tasks landed across backend, frontend,
MCP server, and CI.

### Added

- **CI** — GitHub Actions workflow (`.github/workflows/ci.yml`) covering
  backend pytest + ruff, frontend lint + typecheck + vitest + build, and MCP
  registration tests.
- **Database migrations** — Alembic 0001 baseline + 0002 ambiguity
  resolution columns + 0003 duplicate-flag FK + 0004 analysis indexes.
  Startup now runs `alembic upgrade head` instead of ad-hoc `ALTER` loops.
- **Middleware & errors** — `RequestContextMiddleware` adds `X-Request-ID`
  to every request + log record; global exception handler returns
  `{error, code, request_id}` JSON envelopes consistently.
- **LLM retry helper** — `backend/app/llm/retry.py` adds exponential
  backoff + jitter to every LLM call site, honouring `LLM_TIMEOUT_S` and
  `LLM_RETRY_ATTEMPTS` settings.
- **Orchestration MCP tools** — `list_providers`, `get_tool_config`,
  `update_tool_config`, `test_provider`, `get_provider_capabilities` in
  `mcp-server/tools/orchestration.py`.
- **Frontend build page** — `/documents/[id]/build` now renders build state,
  file registry, snapshot history, and a live SSE activity stream from
  `/api/mcp/sessions/{id}/events/stream`.
- **Toast notifications** — global `<ToastProvider>` + `useToast` hook with
  aria-live notification region. Replaced every `alert()` call site.
- **Tests** — router tests for idea / orchestration / project / activity
  routers, refinement-graph tests with mocked LLM, orchestration e2e tests
  using a stub CLI provider, MCP contract tests for schema + error envelope,
  and a Vitest suite for `apiFetch`, toast store, theme SSR, Modal focus
  trap, and Tabs keyboard navigation.
- **Documentation** — `docs/ARCHITECTURE.md` with mermaid diagrams, plus
  `GUIDE_CURSOR.md`, `GUIDE_CLAUDE_CODE.md`, `GUIDE_WEB_UI.md` shipped
  alongside the existing `MANUAL.md`.

### Changed

- **ORCHESTRATION_STRICT_LLM** now defaults to `true`. Failures on the
  preferred provider surface as errors unless `fallback_chain` explicitly
  includes a viable alternative; the `config_resolver` no longer appends
  `"api"` silently.
- **analyze_document** accepts `?sections=` and runs per-section nodes only
  over the requested indices, keeping prior results for untouched sections.
  Targeted re-analysis deletes only the affected rows.
- **AmbiguityFlagDB** now persists `resolution_text` + `resolved_at`; the
  MCP `resolve_ambiguity` tool and frontend ambiguities page both send /
  display the resolution notes.
- **pipeline_call_llm_json** robustly parses code-fenced, prefixed, or
  otherwise noisy LLM responses; on malformed JSON it retries once with a
  stricter prompt and raises `LLMJSONParseError` if both attempts fail.
- **get_db** skips `commit` on read-only requests for lower latency.
- **List endpoints** (`/api/fs/`, `/api/code/uploads`, library list) accept
  `limit` + `offset` and report `total`. Frontend list pages follow suit.
- **Library** — `suggest_requirements` now fans out Qdrant queries
  concurrently with a bounded semaphore, returning partial results and
  per-section diagnostics on failure.
- **Frontend accessibility** — Tabs use roving tabindex + arrow-key
  navigation, Modal traps focus and restores it on close, SearchInput gains
  aria-label, mobile nav gains a focus trap.
- **Settings page** — editable JSON for `cursor_config` and
  `claude_code_config` with validation and full test-connection error
  surfacing.
- **Agent loop prompt** — every `update_build_state` call now passes
  `current_phase` + `current_task_index`; retry-once guidance is explicitly
  reconciled with the strict go/no-go gate.

### Security

- **Zip-slip** — per-member resolved-path check in the codebase parser plus
  sanitised filenames in `code_router.upload_codebase`. New
  `test_code_upload_security.py` regression suite.
- **LIKE injection** — `document_name` filter on `/api/activity-log` now
  escapes `\`, `%`, and `_` with an explicit `escape='\\'` to the driver.

### Performance

- **Blocking I/O** — file parsers and ZIP extraction run via
  `anyio.to_thread.run_sync` so the event loop stays free under load.
- **Indexes** — new composite / single-column indexes on `fs_id` columns
  across `ambiguity_flags`, `fs_tasks`, `analysis_results`,
  `contradictions`, `edge_cases`, `fs_versions`, `audit_events`.
- **SSE cleanup** — build-event stream releases its DB session promptly.

### New configuration

- `ORCHESTRATION_STRICT_LLM=true` (new default, flipped from `false`).
- `LLM_TIMEOUT_S=120` — per-call LLM timeout.
- `LLM_RETRY_ATTEMPTS=3` — transient-error retries.
- `BACKEND_SELF_URL=http://localhost:8000` — used by the in-process Cursor
  provider health check; override behind reverse proxies or in container
  networks.

---

## 0.1.0 — Baseline

Initial Level-10 + post-L10 implementation: FastAPI backend, Next.js 14
frontend, PostgreSQL + Qdrant infra, LangGraph analysis pipeline (11
nodes), refinement / impact / reverse pipelines, MCP server with ~90 tools,
and orchestration layer for Cursor / Claude Code providers.
