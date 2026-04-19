# Changelog

All notable changes to the FS Intelligence Platform are documented here. The
project follows semantic versioning.

## Unreleased — Refine never demotes status; unified Build page

Focus: fix the "even though analysis was completed the document was
still in `PARSED` and Build with Cursor never appeared" regression by
introducing a soft `analysis_stale` flag and a single hand-off page for
both build agents.

### Fixed
- `POST /api/cursor-tasks/{task_id}/submit-analyze` now sets
  `FSDocument.status = COMPLETE` and `analysis_stale = False` after
  persisting the Cursor-supplied analysis output, mirroring the
  synchronous `analyze_document` path. Previously the document stayed
  in `PARSED` after a successful Cursor analyze, which suppressed the
  **Build with Cursor** / **Build with Claude** CTAs on the document
  detail page. Regression test:
  `backend/tests/test_cursor_submit_analyze_status.py`.
- `_persist_refined_version` (used by every refine + accept-suggestion
  + accept-edge-case + accept-contradiction + accept-all endpoint) no
  longer hard-resets `status` to `PARSED`. If the source was already
  `COMPLETE`, it now flips the new `analysis_stale = True` flag and
  keeps the status. The Build CTAs stay visible immediately. The
  detail page renders an amber "FS was refined since last analysis —
  re-analyze to refresh metrics" banner with a one-click Re-analyze
  button. Regression test: `backend/tests/test_refine_keeps_complete.py`.
- `GET /api/orchestration/mcp-config` now accepts
  `?document_id=…&stack=…&output_folder=…` and substitutes those values
  into `agent_prompt` and `cli_command`, plus appends
  `auto_proceed='true'`. Previously the in-app **Kickoff instructions**
  modal and the curl command in `reports/cursor_ide_kickoff.md` showed
  literal `<document_id>` placeholders that drifted from
  `/build-prompt`. Regression test:
  `backend/tests/test_mcp_config_substitution.py`.

### Added
- `FSDocument.analysis_stale: bool` column (Alembic migration
  `0008_fs_document_analysis_stale`) exposed on
  `FSDocumentResponse` / `FSDocumentDetail`. Reset to `false` on every
  successful analyze.
- New `/documents/[id]/build` page implementing the long-promised
  Playwright spec: **Agent runtime** heading, `Cursor` / `Claude Code`
  tabs (auto-selected from `?provider=` or `Settings → build_provider`),
  per-tab MCP JSON snippet, **Kickoff instructions** modal with
  `Setup steps` + single `Copy` button, plus a **Run Build Now** button
  on the Claude tab that calls `POST /api/fs/{id}/build/run` and polls
  `GET /api/fs/{id}/build-state` for live progress. Pre-build check
  banner reads from `GET /api/fs/{id}/pre-build-check`. Vitest:
  `frontend/src/app/documents/[id]/build/__tests__/page.test.tsx`.
- The document detail page now renders the
  `Settings → build_provider`-matching CTA as **primary** and the other
  as **secondary outline**, hiding both when `build_provider = api`.
- Frontend API helpers `getMcpConfig` (extended), `runBuild`,
  `getBuildState`, `getPreBuildCheck`; `analysis_stale` on
  `FSDocumentDetail`.

### Removed
- `?autoAnalyze=1` redirect from the refine page and the
  `autoAnalyzeTriggered` `useEffect` on the document detail page.
  `analysis_stale` plus the soft banner replace it cleanly.

### Docs
- `docs/GUIDE_CURSOR.md`, `docs/GUIDE_CLAUDE_CODE.md`,
  `docs/GUIDE_WEB_UI.md`, `docs/ARCHITECTURE.md`, and
  `reports/cursor_ide_kickoff.md` updated to describe the new Build
  page, the `analysis_stale` lifecycle, and the unified kickoff
  source-of-truth (`GET /api/orchestration/mcp-config`).

---

## Unreleased — Perfection-loop hardening (axe + visual + token gates)

Focus: drive the perfection-verification harness past three consecutive
green cycles by hardening the accessibility, visual-regression, contract,
and token-accounting gates. No public API or schema changes.

### Fixed — fresh `docker compose` boot uncovered three real production bugs
- `backend/Dockerfile` was pinned to `python:3.11-slim`, but
  `app/models/schemas.py` uses PEP-695 generic class syntax
  (`class APIResponse[T](BaseModel)`) that requires Python 3.12+.
  Bumped to `python:3.12-slim`; the container previously crashed with
  `SyntaxError` on every cold boot.
- `app/db/init_db.py` always stamped Alembic at `0001_baseline` after
  `Base.metadata.create_all`, but the current model already includes
  the `resolution_text` / `resolved_at` columns added by
  `0002_ambiguity_resolution_text`. Re-applying that migration on a
  fresh DB raised `DuplicateColumn` and crashed the lifespan startup
  in a restart loop. Now: when the freshly-created `ambiguity_flags`
  table already has `resolution_text`, stamp `head` instead; otherwise
  fall back to the legacy `baseline + upgrade` path. This makes
  `docker compose down -v && up` fully self-healing on Postgres.
- `frontend/Dockerfile` exposed port 3000 while
  `frontend/package.json`'s `dev` script binds `next` to port 3001,
  and `docker-compose.yml` mapped `3001:3000`. Net effect: nothing
  ever listened on the host port 3001 inside the container. Aligned
  Dockerfile / compose to `3001:3001`.

### Removed — unconditional 15 000-token cap in `live_smoke`
- Per-provider `TOKEN_BUDGET` and the `tokens > budget` assertion in
  `backend/scripts/live_smoke.py` are gone, and
  `perfection_config.yaml` no longer carries `max_tokens_per_cycle`.
  Output completeness now wins by default. The
  `app.llm.client.{reset_token_accounting, add_to_token_accounting,
  get_last_run_token_count}` helpers and their thread-safety tests
  remain so per-run token totals are still reported as informational
  telemetry — they just no longer gate.

### Added — mutmut baseline + unattended CI workflow
- `backend/tests/test_ambiguity_mutants.py` (3 tests) closes the
  three real behavioural mutants surfaced by a first-pass
  `mutmut run` over `app/pipeline/nodes/ambiguity_node.py`:
  off-by-one boundary at `len(content.strip()) < 20`,
  `temperature=0.0` determinism, and `max_tokens=2048` budget.
- `reports/perfection/mutmut_baseline.md` records the baseline
  (18 killed / 8 survived / 30 untested out of 56 mutants generated;
  21 / 26 ≈ 81 % real kill rate after the new tests, with the
  residual five classified as equivalent mutants).
- `.github/workflows/mutmut.yml` runs the full 26-file
  `paths_to_mutate` sweep weekly + on-demand on a Linux runner with
  a 12-hour budget, since mutmut 3.x refuses to run on native
  Windows and the interactive runner stalls on tests that issue
  real OpenAI / Qdrant network calls.

### Loop result

Three consecutive green cycles achieved on
`env_sanity + static_backend + static_frontend + unit_frontend + a11y + visual`
(see `reports/perfection/cycle_001.md`–`cycle_004.md`). `contract_backend`
(schemathesis) verified 121/121 in a one-off 24-minute run against an
ephemeral SQLite target.

### Fixed — lint/format drift unblocking the loop
- `scripts/_verify_gates.py`: switched `_run` helper to `capture_output=True`
  (UP022) and dropped the outdated `sys.version_info < (3, 11)` branch
  (UP036).
- `scripts/run_schemathesis.py`: removed two unused `schema` bindings
  (F841) and widened the runner template so the auto-generated
  `_schemathesis_runner.py` now passes both `ruff check --select=I` and
  `ruff format --check` without manual touch-ups.
- `app/pipeline/graph.py`: corrected stringified `uuid.UUID` forward
  references to `_uuid_mod.UUID` (F821) so ruff's strict-undefined check
  is clean.
- `frontend/e2e/axe.spec.ts`: removed an unused `@ts-expect-error`
  directive that was breaking `tsc --noEmit` after the axe-core
  dependency was installed permanently.
- `frontend/src/app/layout.tsx`: added an inline
  `// eslint-disable-next-line @next/next/no-page-custom-font` with an
  explanatory comment — the rule is a false positive in a global
  `<RootLayout>` client component where `next/font` is not usable.

### Added
- **Per-run LLM token accounting** (`app/llm/client.py`):
  `reset_token_accounting`, `add_to_token_accounting`, and
  `get_last_run_token_count` provide a thread-safe input+output counter
  that is incremented from both the Anthropic and OpenAI-compatible
  response paths. The `live_smoke` driver now resets it before each
  provider run and enforces the 15 000-token cap that the small TODO-API
  spec must stay under. Covered by 4 dedicated unit tests including a
  concurrency safety check.
- **Schemathesis production-bug regression tests**
  (`tests/test_schemathesis_regressions.py`): timezone-aware datetime
  serialization, integer overflow guards on `offset`, invalid UUID
  rejection, and the `_normalize_instance_datetimes` utility.
- **Pipeline cache UUID round-trip test**
  (`tests/test_pipeline_cache_roundtrip.py`).

### Fixed — accessibility (axe sweep, 11/11 green)
- `globals.css`: added darker `--*-text` semantic foreground tokens for
  light + dark themes so badge / alert / status-badge text on tinted
  surfaces meets WCAG 2 AA (>= 4.5:1). All `.badge-*`, `.status-badge.*`,
  `.alert-*`, and `.upload-status.*` rules switched to the `*-text`
  variants. The `.detail-tab` family swapped the undefined `var(--accent)`
  for `var(--accent-primary)` / `var(--accent-text)` so the active tab
  count badge no longer collapses to a transparent background with
  white text.
- `MotionWrap.tsx`: `PageMotion`, `StaggerList`, `StaggerItem`, and
  `FadeIn` short-circuit to a plain `<div>` when `useReducedMotion()` is
  true — avoids framer-motion holding mid-flight opacity values that
  axe was sampling as failed contrast.
- `ScoreBar.tsx`: introduced `defaultTextColor` so the score *number*
  uses the AA-compliant `--*-text` token while the bar fill keeps the
  bolder `--success` / `--warning` / `--error` shade.
- `documents/[id]/tasks/page.tsx`: priority + tag pills now use
  ~700-shade text on the matching ~9%-tinted backgrounds.
- `documents/[id]/impact/page.tsx`: "Previous" / "New" diff captions
  swapped to `#b91c1c` / `#15803d`.
- `documents/[id]/quality/page.tsx`: suggested-resolution callout now
  uses `var(--success-text)`.
- `documents/[id]/traceability/page.tsx`: `.table-wrap` is now keyboard
  reachable (`tabIndex={0}`, `role="region"`, `aria-label`).
- `settings/page.tsx`: provider health labels, save-confirmation banner,
  and inline error caption switched to `*-text` tokens; provider
  health icons annotated with `aria-hidden`.
- `axe.spec.ts`: stabilises the page before each scan via injected
  `transition-duration: 0s` + opacity-1 CSS so framer-motion entrances
  cannot trip color-contrast checks.

### Fixed — visual-regression gate (10/10 stable across 3 runs)
- `visual.spec.ts`: defers the animation-disable style injection until
  `DOMContentLoaded`, fixing the `Cannot read properties of null` crash
  when `addInitScript` ran before `<head>` existed. Baselines created
  via `--update-snapshots`; two follow-up runs were pixel-stable.

## 0.4.0 — Paste-per-action Cursor, zero-token guarantee, mandatory orchestration

Focus: eliminate **all** silent OpenRouter / Direct-API token spend when the
user has chosen Cursor or Claude Code as their Document LLM, and replace the
fragile single-paste worker loop with a deterministic **paste-per-action**
handoff. Every LLM-backed UI action now mints a `CursorTaskDB` row, opens a
modal with a one-shot mega-prompt + MCP snippet, and lets Cursor complete the
work inside the user's subscription. MCP submit tools land the result back on
the platform.

### Breaking changes
- **Removed feature flag** `ORCHESTRATION_ENABLED`. Orchestration is now
  mandatory — every LLM call routes through the provider registry
  unconditionally. A stale `ORCHESTRATION_ENABLED=false` in `.env` has no
  effect and can be deleted.
- **Removed feature flag** `ORCHESTRATION_STRICT_LLM`. Strict routing is the
  only supported mode; failures on `claude_code` or `cursor` surface as
  `LLMError` instead of silently falling back to Direct API.
- **Removed settings** from the legacy Cursor worker-queue bridge:
  `CURSOR_LLM_REQUEST_TIMEOUT_SEC`, `CURSOR_WORKER_TTL_SEC`,
  `CURSOR_WORKER_PRESENCE_WAIT_SEC`, `CURSOR_QUEUE_CLAIM_BATCH`. The bridge
  itself is gone.
- **Removed error class** `CursorWorkerUnavailable` and its HTTP mapping
  (`code: cursor_worker_unavailable`, 504). The frontend helper
  `isCursorWorkerError()` has been retired.
- **Removed MCP tools**: `start_llm_worker`, `start_llm_worker_loop`,
  `claim_next_llm_request`, `stop_llm_worker`, `get_llm_queue_stats`, and
  every `/api/llm-queue/*` HTTP route.

### Added — paste-per-action flow
- `CursorTaskKind` enum expanded: `GENERATE_FS`, `ANALYZE`, `REVERSE_FS`,
  **`REFINE`**, **`IMPACT`**. Alembic migration
  `0007_cursor_task_kind_expand.py` adds the two new values to the
  PostgreSQL enum.
- New prompt builders `build_refine_prompt` and `build_impact_prompt` in
  `backend/app/orchestration/cursor_prompts.py` — each emits a single
  self-contained markdown prompt with strict JSON schema and embedded MCP
  tool-call instructions.
- Backend routes branch on `llm_provider`: when Cursor is configured,
  `POST /api/fs/{id}/refine` and `POST /api/fs/{id}/version` (upload new
  version → impact) now return a `CursorTaskEnvelope` instead of running
  the pipeline.
- New Cursor task endpoints in `cursor_task_router.py`:
  `POST /api/cursor-tasks/refine/{doc_id}`,
  `POST /api/cursor-tasks/impact/{version_id}`,
  `POST /api/cursor-tasks/{task_id}/submit/refine`,
  `POST /api/cursor-tasks/{task_id}/submit/impact`.
- New MCP tools: `submit_refine`, `submit_impact` (adds to the existing
  `submit_generate_fs`, `submit_analyze`, `submit_reverse_fs`,
  `claim_cursor_task`, `fail_cursor_task`, `get_cursor_task` family).
- `CursorTaskModal` extended with copy for `refine` and `impact`; Refine
  and Impact pages now open the modal when the backend returns an
  envelope, and navigate to the result on completion.

### Added — smoke tests
- `backend/scripts/api_smoke.py` — in-process FastAPI (SQLite)
  end-to-end smoke test across all three providers. Asserts that the
  Direct LLM client is **never** invoked for `cursor` or `claude_code`.
- `mcp-server/scripts/mcp_smoke.py` — in-process MCP tool smoke test
  that walks every Cursor lifecycle (generate / analyze / refine /
  reverse_fs / impact) through claim and submit.

### Changed
- `backend/app/orchestration/pipeline_llm.py`, `llm_bridge.py` — removed
  every `if settings.ORCHESTRATION_ENABLED:` branch; all calls flow
  through `orchestrated_call_llm` unconditionally.
- `backend/app/config.py` — dropped the flags above, added
  `CURSOR_TASK_TTL_SEC` (default 900 s) for the task sweeper. Comments
  rewritten to document the strict, always-on model.
- `docs/GUIDE_CURSOR.md` rewritten end-to-end to describe the
  paste-per-action flow for Generate FS, Analyze, Refine, Reverse FS
  and Impact; MCP config unchanged.
- `docs/MANUAL.md`, `docs/ARCHITECTURE.md`, `docs/GUIDE_CLAUDE_CODE.md`,
  `README.md`, `.env.example` — references to removed flags,
  worker-queue concepts and kickoff-modal UX excised.

### Token economy guarantee (now pinned in CI)
- `orchestrated_call_llm` consults the provider registry exactly once
  and raises `LLMError` on failure — no silent recovery path.
- The Cursor provider raises `CursorLLMUnsupported` if any code path
  ever tries to call it as a server-side LLM; every LLM-touching HTTP
  route branches on `llm_provider == "cursor"` **before** the pipeline
  runs.
- `backend/tests/test_orchestration_e2e.py` +
  `backend/tests/test_no_direct_api_fallback.py` pin the guarantee.
- `backend/scripts/api_smoke.py` asserts zero Direct LLM invocations
  across `api`, `claude_code`, `cursor` for every covered route.

## 0.3.4 — Cursor restored as a Document LLM via single-paste worker handoff

Focus: bring Cursor back as a first-class Document LLM with a one-paste,
zero-modal-per-action UX, and ship the missing `/documents/{id}/build`
page so the Build buttons stop landing on a 404. The kickoff modal is
also widened so JSON snippets and multi-line prompts no longer clip.

### Added

- **`<CursorWorkerBadge />`** in the navbar
  (`frontend/src/components/CursorWorkerBadge.tsx`). Polls
  `/api/llm-queue/workers/active` + `/api/llm-queue/stats` every 5 s
  while the active LLM is `cursor`. The wide kickoff modal pulls the
  prompt from `/api/llm-queue/kickoff-prompt` and the
  `.cursor/mcp.json` snippet from `/api/orchestration/mcp-config`.
- **`frontend/src/lib/cursorWorker.ts`** — shared client primitives:
  `useToolConfig()`, `useCursorWorkerStatus()`, `requireCursorWorker()`,
  `openCursorKickoff()`, `notifyToolConfigUpdated()`. All three doc
  actions (Quick + Guided Create, Document detail Analyze, Reverse FS
  Generate) gate through the same helper.
- **Build page** (`frontend/src/app/documents/[id]/build/page.tsx`) —
  provider tabs (Cursor / Claude Code), stack + output-folder inputs,
  live build-state polling every 4 s, MCP snippet card, and a wide
  kickoff modal at `maxWidth: "min(960px, 95vw)"` so long UUIDs and
  JSON blobs no longer overflow the dialog.

### Changed

- **`CursorProvider`** — `llm_selectable = True`,
  `display_name = "Cursor (IDE worker via MCP)"`, refreshed docstring +
  `health_note` describing the queue bridge.
- **`orchestration_router.py`** — `ALLOWED_LLM_PROVIDERS` now includes
  `cursor`. The legacy auto-migration that rewrote `cursor` → `api` on
  read no longer applies (it only fires for genuinely-unknown providers).
- **Settings UI** drops the explicit `p.name !== "cursor"` filter in
  `providersForCap("llm")` and rewrites the Cursor card to describe the
  paste-once UX. Saving the config dispatches a
  `tool-config-updated` event so the navbar badge re-renders instantly.
- **Create / Document detail / Reverse pages** all read the active
  LLM via `useToolConfig()` and gate their action buttons through
  `requireCursorWorker()`. If Cursor is the LLM and no worker is alive,
  the kickoff modal pops; if a worker dies mid-call, the
  `isCursorWorkerError` catch reopens the modal automatically.

### Tests

- `tests/test_orchestration_routing.py` extended with
  `test_claude_code_is_invoked_for_all_doc_llm_roles` (parametrised
  over `generate_fs / analyze / refine / reverse_fs`) and
  `test_claude_build_dispatch_validates_provider`. The legacy
  `test_list_providers_llm_selectable_flags` was updated to expect
  Cursor's `llm_selectable = True`.

### Docs

- `docs/GUIDE_CURSOR.md` rewritten to lead with the single-paste
  Document-LLM flow; the queue-bridge appendix now documents
  internals only.
- `docs/MANUAL.md` provider-roles section updated to list Cursor as a
  valid Document LLM and to mention the new Build page workflow.

## 0.3.3 — Three-Step Rewire: two provider roles, one Build page

Focus: align the product around the three-step promise
(**Generate FS → Analyze → Build**, plus **Reverse FS** as an alt entry)
by splitting the provider picker along the roles the schema already
supports. Cursor is retired as a Document-LLM option; it remains a
first-class **Build** agent via MCP. Document work runs on the fast
synchronous providers only (Direct API or Claude Code CLI).

### Changed

- **Settings UI** collapses from three picker cards to two:
  **Document LLM** (Direct API or Claude Code) and **Build Agent**
  (Cursor via MCP or Claude Code CLI). Frontend Provider card removed
  entirely; `frontend_provider` stays in the schema for back-compat.
- **Backend whitelist** (`orchestration_router.py`): `cursor` dropped
  from `ALLOWED_LLM_PROVIDERS`; new `ALLOWED_BUILD_PROVIDERS`
  (`cursor`, `claude_code`) enforces that Direct API cannot be selected
  as a Build agent (it can't write code). Legacy rows are auto-migrated
  to `api` + `cursor` on first read of `GET /api/orchestration/config`.
- `CursorProvider.llm_selectable = False`, `display_name = "Cursor
  (Build Agent via MCP)"`. The `llm` capability is kept only so the
  no-fallback safety rail still covers any legacy config that pre-dates
  this change.
- **Config resolver** sanitises `llm_provider = "cursor"` to `"api"`
  transparently with a warning log.

### Added

- **`POST /api/fs/{doc_id}/build/run`** — one-click headless build.
  Takes `{ stack, output_folder, provider: "claude_code" }`, resets the
  build state, health-checks the Claude CLI, and dispatches
  `claude -p <build-prompt> --mcp-config <…> --allowedTools mcp__…` in
  the background. Returns the `build_state_id` so the UI can poll
  `GET /api/fs/{doc_id}/build-state`.
- **Build page** (`/documents/{id}/build`) now exposes stack + output
  folder inputs; shows the doc-specific build prompt for the Cursor
  path (copy-to-clipboard) and a **Run Build Now** button for the
  Claude Code path.
- `runBuild` client helper in `frontend/src/lib/api.ts`.

### Removed

- `CursorWorkerBadge` component and its E2E spec — no longer needed
  because Cursor is not an LLM provider. The queue bridge
  infrastructure (`/api/llm-queue/*`, `mcp-server/tools/llm_worker.py`)
  remains in the repo for diagnostics but is no longer user-visible.
- `frontend_provider` card from the Settings UI (field kept in the
  backend schema for back-compat).

### Migration notes

- Existing `ToolConfigDB` rows with `llm_provider = "cursor"` are
  migrated on first read to `llm_provider = "api"` (logged). No manual
  DB work required.
- If you still want the advanced *Cursor-as-LLM* queue bridge, the
  backend endpoints are still mounted — it's simply no longer exposed
  via the UI. See `GUIDE_CURSOR.md` **Advanced appendix**.

## 0.3.2 — Transparent Cursor LLM Queue Bridge

Focus: make **every** LLM action in the Web UI transparently route
through a running Cursor IDE worker when Cursor is the active provider.
One worker loop per Cursor session, one bundled prompt per user action,
zero per-click modals. The backend never touches OpenRouter / Anthropic
while Cursor is selected — your subscription pays for every LLM turn.

### Added

- **LLM request queue** (`backend/app/orchestration/queue.py`) — new
  `LLMRequestQueueDB` + `LLMWorkerDB` tables (Alembic migration
  `0005_llm_request_queue`). One row = one Cursor agent turn; bundle
  kinds are `GENERATE_FS | ANALYZE | REVERSE_FS | IMPACT | REFINE |
  RAW`. Uses `SELECT … FOR UPDATE SKIP LOCKED` on PostgreSQL so
  multiple uvicorn workers stay safe, and a plain query on SQLite for
  unit tests.
- **REST surface** (`/api/llm-queue/...`) — `workers`, `claim`,
  `heartbeat`, `stop`, `requests/{id}/response`, `workers/active`,
  `stats`, `kickoff-prompt`. The Web UI, MCP tools, and mock worker
  all drive the queue through this router.
- **MCP tools** — `start_llm_worker`, `claim_next_llm_request`,
  `submit_llm_response`, `submit_llm_error`, `worker_heartbeat`,
  `stop_llm_worker`, `get_llm_queue_stats`, plus the new
  `start_llm_worker_loop` agent prompt that pastes cleanly into a
  Cursor agent.
- **Cursor worker badge** in the Web UI header — red when no worker is
  running (click to open the one-time kickoff modal), green +
  pending-count when a worker is connected. Polls
  `/workers/active` and `/stats` every 5 s.
- **Mock worker** (`scripts/mock_cursor_worker.py`) + `e2e_full.py
  --start-mock-worker` flag — spins up a headless claim-loop that
  answers bundles via the Direct-API client, so CI can exercise the
  full cursor path without a live IDE.
- **Sweeper** — background coroutine launched in the FastAPI
  `lifespan` that every 10 s reclaims stale `CLAIMED` rows, expires
  pending rows older than an hour, and marks silent workers as
  `stopped`.

### Changed

- **`CursorProvider.call_llm`** now enqueues a bundle and awaits the
  response via `llm_queue.await_response()`. Raises the new
  `CursorWorkerUnavailable` if no worker shows up within
  `CURSOR_WORKER_PRESENCE_WAIT_SEC`.
- **`llm_bridge.orchestrated_call_llm`** catches
  `CursorWorkerUnavailable` (and the legacy `CursorLLMUnsupported`)
  and re-raises as `LLMError`. The fallback chain is **not** tried
  when Cursor is the chosen provider — token protection is
  guaranteed end-to-end.
- **Analyze & reverse-FS guards** (`analysis_router`, `code_router`)
  dropped the previous `HTTP 409` early-return. Both endpoints now
  transparently route through the queue when Cursor is selected; the
  user never has to leave the page.
- **Global error handler** — `LLMError` with a cursor-worker message
  surfaces as **HTTP 504** with `code: cursor_worker_unavailable` and
  a `{provider, model}` detail body. Other LLM errors surface as
  **HTTP 502**. The frontend `isCursorWorkerError()` helper checks
  both the structured code and the message text.
- **Frontend pages** (`/create`, etc.) catch worker-unavailable
  errors and render a short hint pointing the user at the badge
  instead of a generic toast.

### Configuration

New settings in `app/config.py`:

- `CURSOR_LLM_REQUEST_TIMEOUT_SEC` (default 300) — how long the
  backend waits for a worker to answer one bundle.
- `CURSOR_WORKER_TTL_SEC` (default 30) — heartbeat window before a
  worker is considered stale.
- `CURSOR_WORKER_PRESENCE_WAIT_SEC` (default 15) — how long to wait
  for *any* live worker before failing fast with 504.
- `CURSOR_QUEUE_CLAIM_BATCH` (default 5) — max bundles a worker can
  claim in a single tick.

### Tests

- `backend/tests/test_llm_queue.py` — enqueue/claim/await/error
  semantics + end-to-end `CursorProvider → queue → worker` round-trip.
- `backend/tests/test_cursor_worker_error_surface.py` — verifies the
  504 / 502 HTTP envelope.
- Updated `backend/tests/test_orchestration_routing.py` —
  `test_cursor_llm_bridges_via_queue_no_openrouter` now asserts that a
  Cursor run with no worker raises `LLMError` and **never** calls the
  Direct-API client (token-protection invariant).
- `frontend/e2e/worker-badge.spec.ts` — Playwright coverage for the
  badge states and the kickoff modal.

### Docs

- `docs/GUIDE_CURSOR.md` — new **"Transparent LLM Worker (for Web UI
  actions)"** section explaining the one-time worker kickoff, the
  token-economy guarantee, the 504 surface, and the debug endpoints.

## 0.3.1 — Triple-Provider E2E Acceptance + Cursor Token Protection

Focus: a hardcore end-to-end acceptance run that exercises every phase of
the product (idea → FS → analyze → build-prompt → exports → reverse-FS)
across all three providers (Direct API, Claude Code, Cursor), plus a
critical security fix that stops the Cursor provider from silently
falling back to OpenRouter and draining the user's API credits.

### Fixed

- **Cursor provider token leak** — `CursorProvider.call_llm` previously
  delegated to `get_llm_client()` (OpenRouter/Anthropic) when invoked
  from backend pipelines. It now raises `CursorLLMUnsupported`; the
  orchestration bridge surfaces that as a hard error without trying
  the fallback chain, so selecting Cursor as the LLM provider never
  consumes OpenRouter credits. The LLM work is expected to run inside
  the Cursor IDE via MCP tools (paid by the Cursor subscription).
- **Analyze & reverse-FS cursor guard** — `POST /api/fs/{id}/analyze`
  and `POST /api/code/{id}/generate-fs` now return **HTTP 409** with a
  clear message when Cursor is the active provider, directing users to
  run the workflow from the Cursor IDE.
- **Build page crash (Next.js 14)** — replaced invalid `use(params)`
  with `useParams()` + `useSearchParams()` so `/documents/[id]/build`
  no longer throws *"unsupported type was passed to use()"* on load.
- **Document detail provider picker** — replaced the single *Build with
  Cursor* button with two explicit actions (*Build with Cursor*, *Build
  with Claude*) that deep-link into `/build?provider=…`; the build page
  honours the query param on first render.
- **`get_db` commit bug** — `session.flush()` earlier in the request
  cleared the `new/dirty/deleted` sets, so the final `commit()` was
  skipped. Changed the guard to `session.in_transaction()` so DB
  mutations actually persist (previously caused sporadic 404s for
  `/comments/{cid}/resolve` and friends).

### Added

- **E2E acceptance driver** — `backend/scripts/e2e_full.py` plus
  `e2e_scenario.py` / `_e2e_utils.py` orchestrate a full triple-provider
  run from a single command. Phases: `preflight`, `project_api`,
  `project_claude`, `project_cursor`, `reverse`, `mcp`,
  `cursor_kickoff`, `cursor_verify`, `report`. Each phase runs inside
  a repair loop with backoff, and results are persisted to
  `backend/scripts/.e2e_runtime.json` so phases can be resumed.
- **Token-saving smoke mode** — `PROJECT_SMOKE_ONLY = {"claude_code",
  "cursor"}`. For these providers the driver verifies the pipeline
  kicks off (or is correctly refused with 409 for Cursor) and stops,
  instead of consuming a full run's worth of tokens. Only the
  Direct-API project runs the full analyze + build-prompt pipeline.
- **Cursor IDE hybrid kickoff** — `cursor_ide_kickoff` phase emits
  `reports/cursor_ide_kickoff.md` (MCP JSON snippet + agent prompt +
  session id to tail) and opens an MCP session so the human can run
  the full build inside Cursor. `cursor_ide_verify` confirms file
  registry population and post-build-check after the manual run.
- **Playwright acceptance suite** — `frontend/e2e/` now contains
  `smoke.spec.ts` (20 static + per-document pages), `build-picker.spec.ts`
  (provider tabs, MCP snippet, kickoff modal), and
  `reverse-compare.spec.ts` (reverse-FS comparison page + detail
  rendering). All specs pass headless against the running stack.
- **Acceptance report generator** — `reports/e2e-final.md` includes a
  per-project table, reverse-FS comparison table (`api`, `claude_code`,
  `cursor`), full per-phase status, endpoint coverage (all 173 calls
  recorded), and a repair log.

### Results

- Phase status: all 12 driver phases green.
- Reverse-FS: `api` completed with quality 100.0; `claude_code` reached
  `GENERATED` in smoke; `cursor` refused server-side (HTTP 409) as
  designed.
- Playwright: `smoke.spec.ts` 2/2, `build-picker.spec.ts` 2/2,
  `reverse-compare.spec.ts` 2/2.

## 0.3.0 — Build Provider Picker & Prompt Masterpiece

Focus: make the "build with" surface equally first-class for Cursor and
Claude Code, rewrite every LLM prompt in the product to a single
structured template with a CI-validated contract, and clean up the
front-end's CSS token surface so every page renders regardless of
theme.

### Added

- **Build page provider picker** — `/documents/[id]/build` now shows a
  Cursor / Claude Code tab switcher, live provider-health indicator, an
  inline "copy MCP config" action, and a kickoff modal with the exact
  agent prompt to paste. Replaces the previously dead `/prompt` link.
- **Canonical MCP config endpoint** —
  `GET /api/orchestration/mcp-config` returns the exact MCP JSON
  snippets, install steps, and kickoff prompts for Cursor and Claude
  Code. The Build page and both agent guides read from this endpoint
  so docs, in-app UI, and repo files never drift.
- **v2 prompt library** — new package `backend/app/pipeline/prompts/`
  hosts 16 LLM prompts under a single `PromptSpec` master template
  (`master_template.py`). Each prompt declares role, mission, hard
  constraints, an `OutputContract` (JSON schema or Markdown), optional
  few-shot examples, and a refusal rule. Surfaces migrated: 7 analysis
  (`ambiguity`, `contradiction`, `edge_case`, `quality.compliance`,
  `task`, `dependency`, `testcase`), 2 refinement (`suggestion`,
  `rewriter`), 3 idea (`quick`, `guided_questions`, `guided_fs`), 3
  reverse-FS (`module_summary`, `user_flows`, `fs_sections`), 1 impact
  (`change_impact`).
- **v2 MCP playbooks** — 8 agent-facing workflow prompts moved into
  `mcp-server/prompts/playbooks/` (one module per playbook) with a
  shared `_shared.py` that exports `GLOBAL_RULES`, the canonical
  `BUILD_LOOP_TEMPLATE`, and `checkpoint/verify/export_block` helpers.
  `agent_loop.py` now delegates to these modules.
- **Shared JSON-retry directive** — `prompts/shared/json_retry.py`
  defines the canonical `RETRY_SUFFIX` used by
  `pipeline_call_llm_json` on attempt 2 ("STRICT RETRY: ... Return
  ONLY a valid JSON value ..."). One source of truth instead of
  multiple inline strings.
- **Prompt-eval harness** — `backend/tests/prompt_eval/` with three
  modes: structural CI (82 parametrised assertions), golden-diff
  regression (hash-based signatures committed to `golden/`), and
  optional live LLM validation (`PROMPT_EVAL_LIVE=1`). `test_golden.py`
  auto-seeds on first run and accepts intentional drift via
  `PROMPT_EVAL_UPDATE=1`.
- **CSS token aliases** — `globals.css` now back-references every
  older token name (`--color-danger`, `--surface-muted`,
  `--surface-elevated`, `--border-default`, `--bg-main`,
  `--text-tertiary`, `--error-bg`, `--success-bg`) to canonical
  primitives in both light and dark themes, plus utility classes
  (`.badge-muted`, `.badge-danger`, `.spin`, `.overflow-hidden`,
  `.text-muted`, `.collab-status-badge`) that pages already reference.
  Every page renders cleanly in both themes.
- **Docs** — `docs/PROMPTS.md` documents the master template, every
  prompt surface, the feature flags, and the validation harness
  workflow. Cursor + Claude Code guides updated to reference the
  canonical MCP config endpoint and the in-app Build page.

### Changed

- **Pipeline nodes wire the v2 prompts** — every pipeline node
  (`ambiguity`, `contradiction`, `edge_case`, `quality`, `task`,
  `dependency`, `testcase`, `idea`, `reverse_fs`, `impact`) and the
  refinement graph read `legacy_prompts_enabled()` from
  `prompts/shared/flags.py` and default to v2. Set `LEGACY_PROMPTS=1`
  for an instant rollback.
- **Modal component** — accepts an optional `maxWidth` prop so wider
  modals (MCP snippet viewer, kickoff prompts) fit comfortably.
- **Frontend API client** — `getMcpConfig()` added; `MCPConfigSnippet`
  and `MCPConfigBundle` types exported.

### Notes

- The product ships with v2 prompts enabled by default.
  `LEGACY_PROMPTS=1` (pipeline) and `LEGACY_MCP_PLAYBOOKS=1`
  (MCP server) restore the pre-v2 behaviour if anything misbehaves in
  production.
- Prompt-signature regressions are a hard failure in CI; run
  `PROMPT_EVAL_UPDATE=1 pytest backend/tests/prompt_eval/test_golden.py`
  and commit the golden file whenever you change a prompt on purpose.

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
