# Web UI -- Direct API Workflow Guide

The web UI with Direct API is the default way to use the FS Intelligence Platform. You configure your LLM API keys, and the platform handles everything through the browser: idea generation, analysis, refinement, and export. Build is not available through Direct API (use Claude Code or Cursor for builds).

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
5. The system creates a new version and re-analyzes automatically.

---

## Step 7: Accept and Resolve Issues

For individual issues:

- **Edge cases**: Click **Accept** to merge the suggested addition into the FS text.
- **Contradictions**: Click **Accept** to merge the suggested resolution.
- **Ambiguities**: Click **Resolve** to mark as addressed (ambiguities have clarification questions, not text fixes).
- **Bulk operations**: Use **Accept All** or **Resolve All** for batch processing.

After resolving issues, the quality score updates automatically.

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
