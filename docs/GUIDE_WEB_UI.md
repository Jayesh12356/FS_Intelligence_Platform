# Web UI -- Direct API Workflow Guide

The web UI with Direct API is the default way to use the FS
Intelligence Platform. You configure your LLM API keys, and the
platform handles everything through the browser: idea generation,
analysis, refinement, and export.

**Two roles, three providers.** Settings now asks two questions:

1. **Document LLM** — who powers Generate FS, Analyze, Refine,
   Reverse FS and Impact? Pick **Direct API** (this guide,
   synchronous, server-side), **Claude Code** (synchronous, local
   CLI), or **Cursor** (paste-per-action handoff — every UI action
   opens a modal with a mega-prompt you paste into Cursor's Agent).
2. **Build Agent** — who writes the code? **Cursor** (paste the
   build prompt into a Cursor Agent chat) or **Claude Code**
   (headless, one-click from the Build page). Direct API is not a
   valid Build Agent.

Pair Direct API with Cursor or Claude Code to reach the Build step.
See [GUIDE_CURSOR.md](./GUIDE_CURSOR.md) and
[GUIDE_CLAUDE_CODE.md](./GUIDE_CLAUDE_CODE.md).

---

## Prerequisites

| Requirement | How to get it |
|-------------|---------------|
| LLM API key | At least one: Anthropic, OpenAI, Groq, or OpenRouter |
| Platform running | `docker compose up` (backend + frontend + database + Qdrant) |
| Frontend | `http://localhost:3000` |
| Backend | `http://localhost:8000` |

---

## Step 1: Configure API Keys

Edit your `.env` file (or set environment variables):

```bash
# Pick one provider
LLM_PROVIDER=anthropic          # or openai, groq, openrouter

# Set the matching key
ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GROQ_API_KEY=gsk_...
# OPENROUTER_API_KEY=sk-or-...

# Primary model
PRIMARY_MODEL=claude-sonnet-4-20250514
```

For **OpenRouter**, you can also set role-specific models:

```bash
REASONING_MODEL=deepseek/deepseek-v3.2-speciale
BUILD_MODEL=minimax/minimax-m2.7
LONGCONTEXT_MODEL=google/gemini-3-flash-preview
FALLBACK_MODEL=deepseek/deepseek-v3.2
```

Restart the backend after changing keys.

---

## Step 2: Verify Provider Health

1. Go to `http://localhost:3000/settings`.
2. Confirm **Direct API (Multi-Provider)** is selected under LLM Provider.
3. Click **Test All** to verify connectivity.
4. You should see a green checkmark next to "Direct API".

---

## Step 3: Generate an FS from an Idea

1. Go to `http://localhost:3000/create`.
2. Choose a mode:

### Quick Create
- Enter your product idea (at least 10 characters).
- Optionally select industry and complexity.
- Click **Generate Functional Specification**.
- You will be redirected to the document page.

### Guided Create
- Enter your idea and click **Start Guided Discovery**.
- Answer the 6 discovery questions tailored to your idea.
- Click **Generate Functional Specification**.
- The FS is generated using your answers for maximum specificity.

---

## Step 4: Analyze the Document

1. On the document page (`/documents/{id}`), click **Analyze**.
2. The 11-node analysis pipeline runs:
   - Ambiguity detection
   - Adversarial debate (CrewAI multi-agent)
   - Contradiction analysis
   - Edge case detection
   - Quality scoring
   - Task decomposition
   - Dependency mapping
   - Traceability matrix
   - Duplicate detection
   - Test case generation
3. Watch the progress stepper update in real time.
4. When complete, review the results on the document page.

---

## Step 5: Review Results

The document page shows:

| Section | What to look for |
|---------|------------------|
| **Quality Score** | Overall score (aim for >= 90). Sub-scores: completeness, clarity, consistency. |
| **Ambiguities** | Flagged vague requirements with severity (LOW/MEDIUM/HIGH). Resolve HIGH flags before building. |
| **Contradictions** | Conflicting statements between sections with suggested resolutions. |
| **Edge Cases** | Missing error handling, boundary conditions, negative paths. |
| **Tasks** | Atomic developer tasks with effort estimates, acceptance criteria, and section traceability. |
| **Dependencies** | Task ordering with parallel execution opportunities. |
| **Test Cases** | Generated test cases (unit, integration, E2E, acceptance) per task. |

---

## Step 6: Refine the Document

If the quality score is below 90:

1. Click **Refine** on the document page.
2. Choose mode: **Auto** (system picks), **Targeted** (per-issue fixes), or **Full** (complete rewrite).
3. Review the side-by-side diff of original vs refined text.
4. Click **Accept** to merge the refined text into the document.
5. The platform creates a new version and **keeps the document in
   `COMPLETE`** so the Build CTA stays visible. A soft amber banner
   appears on the detail page — *"FS was refined since the last
   analysis. Re-analyze to refresh metrics."* — with a one-click
   **Re-analyze** button. You can ship now and refresh metrics later,
   or click Re-analyze first and then build.

> Behind the scenes the FSDocument now carries an `analysis_stale`
> boolean that flips to `true` on every refine / accept-suggestion /
> accept-edge-case / accept-contradiction / accept-all and is reset to
> `false` by the next successful analyze run. Status is **never** demoted
> to `PARSED` after a successful analysis (regression coverage:
> [`backend/tests/test_refine_keeps_complete.py`](../backend/tests/test_refine_keeps_complete.py)).

---

## Step 7: Accept and Resolve Issues

For individual issues:

- **Edge cases**: Click **Accept** to merge the suggested addition into the FS text.
- **Contradictions**: Click **Accept** to merge the suggested resolution.
- **Ambiguities**: Click **Resolve** to mark as addressed (ambiguities have clarification questions, not text fixes).
- **Bulk operations**: Use **Accept All** or **Resolve All** for batch processing.

After resolving issues, the quality score updates automatically.

---

## Step 7.5: Hand off to a Build Agent

Once the document reaches `COMPLETE` (regardless of whether
`analysis_stale` is set), the document detail page exposes two CTAs:

- **Build with Cursor** → `/documents/{id}/build?provider=cursor`
- **Build with Claude** → `/documents/{id}/build?provider=claude_code`

The button matching your saved `Settings → Build Agent` is rendered as
the **primary** action; the other becomes a secondary outline button so
you can override per document. If `build_provider = api` (the only
non-build provider), both CTAs are hidden — Direct API is never a valid
build runtime.

The Build page itself (`/documents/{id}/build`) shows:

1. A **pre-build check** banner (open ambiguities / contradictions /
   missing tasks).
2. Inputs for `Stack` and `Output folder` that flow into the snippet.
3. **Agent runtime** tabs (`Cursor`, `Claude Code`) — switch the URL
   `?provider=` and re-render the MCP JSON snippet + agent prompt /
   CLI command.
4. A **Kickoff instructions** modal with step-by-step setup and a
   single **Copy** button.
5. On the Claude tab, a **Run Build Now** button that calls
   `POST /api/fs/{id}/build/run` and polls the live `build-state`
   stream below the tabs.

Everything on this page is rendered from
`GET /api/orchestration/mcp-config?document_id=…&stack=…&output_folder=…`,
so the snippet you copy is the same one Cursor/Claude see at runtime.

---

## Step 8: Export

| Format | How |
|--------|-----|
| **JIRA** | Document page → Export → JIRA. Creates epics and stories from tasks. |
| **Confluence** | Document page → Export → Confluence. Publishes full analysis report. |
| **PDF** | Document page → Export → PDF. Styled intelligence report. |
| **DOCX** | Document page → Export → DOCX. Editable Word document. |
| **Test Cases CSV** | Document page → Test Cases → Export CSV. |

---

## Upload an Existing FS Document

Instead of generating from an idea, you can upload an existing specification:

1. Go to `http://localhost:3000/upload`.
2. Upload a `.pdf`, `.docx`, or `.txt` file.
3. The system parses it into structured sections.
4. Proceed to **Analyze** as in Step 4.

---

## Reverse FS from Code

For legacy systems with no documentation:

1. Go to `http://localhost:3000/reverse`.
2. Upload a `.zip` file of your codebase.
3. The system extracts code entities and generates an FS through a 4-step LLM pipeline.
4. Review the generated FS and import it as a document for full analysis.

---

## Change Impact Analysis

When requirements change:

1. On the document page, click **Upload New Version**.
2. Upload the revised FS file.
3. The system diffs sections, classifies task impact (INVALIDATED / REQUIRES_REVIEW / UNAFFECTED), and estimates rework days.
4. Review the impact report and decide which tasks need re-implementation.

---

## What Direct API Cannot Do

Direct API handles all analysis, refinement, and export workflows. It does **not** support autonomous code generation (builds). For builds, use:

- **Claude Code** -- Fully headless autonomous builds from terminal via CLI + MCP.
- **Cursor** -- MCP-driven builds inside the IDE with full visibility.

See `docs/GUIDE_CLAUDE_CODE.md` and `docs/GUIDE_CURSOR.md` for build workflows.
