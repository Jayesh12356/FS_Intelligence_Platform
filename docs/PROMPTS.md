# Prompt Engineering Reference

Every LLM prompt the FS Intelligence Platform uses is defined in one of
two places:

1. **`backend/app/pipeline/prompts/`** — v2 prompts used by LangGraph
   pipeline nodes and the refinement graph. Each prompt is built from a
   structured `PromptSpec` so role, mission, constraints, output
   contract, and refusal behaviour are uniform across 16 surfaces.
2. **`mcp-server/prompts/playbooks/`** — v2 playbook prompts returned
   by the MCP server to agents (Cursor, Claude Code). Each playbook is
   a standalone workflow with explicit exit criteria.

This document is the single reference for how prompts are authored,
validated, and rolled out safely.

---

## 1. Master Template (`PromptSpec`)

Location: `backend/app/pipeline/prompts/master_template.py`.

Every pipeline prompt is a `PromptSpec` instance:

```python
SPEC = PromptSpec(
    name="analysis.ambiguity",
    role="You are an expert requirements analyst...",
    mission="Detect and classify every ambiguity in one section.",
    constraints=[
        "Emit only items whose flagged_text is a verbatim substring.",
        "Use HIGH severity when a reasonable developer could implement...",
        ...
    ],
    output_contract=OutputContract(
        shape=OutputShape.JSON_ARRAY,
        schema={...},
        empty_value="[]",
    ),
    few_shot=[FewShotExample(label="...", input_snippet="...", expected_output="...")],
    refusal="If the section has no ambiguities, return `[]`.",
)
```

The template renders a deterministic system prompt with these sections,
in order:

- Role paragraph (no "as an AI" voice).
- `MISSION —` one sentence.
- `HARD CONSTRAINTS` bullet list.
- Optional extras.
- `OUTPUT CONTRACT` with shape + JSON schema (for JSON shapes).
- `EXAMPLES` (when few-shot is provided).
- `REFUSAL` block describing behaviour on malformed input.

The matching user prompt (`spec.user(body)`) always ends with a
one-line reminder of the contract shape, which meaningfully reduces
"I'll write JSON in a code fence" drift.

---

## 2. Prompt Surfaces (16 total, v2)

| Category | Module | Surface name |
|----------|--------|--------------|
| Analysis | `prompts/analysis/ambiguity.py` | `analysis.ambiguity` |
| Analysis | `prompts/analysis/contradiction.py` | `analysis.contradiction` |
| Analysis | `prompts/analysis/edge_case.py` | `analysis.edge_case` |
| Analysis | `prompts/analysis/quality.py` | `analysis.quality.compliance` |
| Analysis | `prompts/analysis/task.py` | `analysis.task` |
| Analysis | `prompts/analysis/dependency.py` | `analysis.dependency` |
| Analysis | `prompts/analysis/testcase.py` | `analysis.testcase` |
| Refinement | `prompts/refinement/suggestion.py` | `refinement.suggestion` |
| Refinement | `prompts/refinement/rewriter.py` | `refinement.rewriter` |
| Idea | `prompts/idea/quick.py` | `idea.quick` |
| Idea | `prompts/idea/guided_questions.py` | `idea.guided_questions` |
| Idea | `prompts/idea/guided_fs.py` | `idea.guided_fs` |
| Reverse FS | `prompts/reverse/module_summary.py` | `reverse.module_summary` |
| Reverse FS | `prompts/reverse/user_flows.py` | `reverse.user_flows` |
| Reverse FS | `prompts/reverse/fs_sections.py` | `reverse.fs_sections` |
| Impact | `prompts/impact/change_impact.py` | `impact.change_impact` |

In addition, the shared retry directive lives at
`prompts/shared/json_retry.py` (`shared.json_retry`). It is appended to
the user prompt on the second attempt when the first reply is not
parseable JSON.

### MCP Playbook Prompts (8 total, v2)

Playbooks are workflow prompts returned to agents (Cursor, Claude
Code) that drive multi-step autonomous sessions. Each lives in its own
module under `mcp-server/prompts/playbooks/` and is registered via
`mcp-server/prompts/agent_loop.py`:

| Playbook | Module | Purpose |
|----------|--------|---------|
| `start_build_loop` | `playbooks/build_loop.py` | Audit → plan → build → verify for one FS. |
| `start_full_autonomous_loop` | `playbooks/full_autonomous.py` | Idea → production, zero-touch. |
| `refine_and_analyze` | `playbooks/refine_analyze.py` | Tight refine → accept → re-analyze loop. |
| `fix_single_ambiguity` | `playbooks/fix_ambiguity.py` | Deterministic one-flag resolution. |
| `implement_task` | `playbooks/implement_task.py` | Single-task implement + verify. |
| `handle_requirement_change` | `playbooks/requirement_change.py` | Safe new/changed requirement flow with rollback. |
| `quick_analysis` | `playbooks/quick_analysis.py` | Analyze + resolve + report, no build. |
| `project_overview` | `playbooks/project_overview.py` | Platform-wide dashboard. |

All playbooks share a `_shared.py` module that exports:

- `GLOBAL_RULES` — the "never write code before IMPLEMENT, only
  transient errors get one retry, update_build_state must include
  current_phase and current_task_index" block.
- `BUILD_LOOP_TEMPLATE` — the canonical per-task loop (SKIP CHECK,
  REUSE CHECK, CONTEXT, IMPLEMENT, REGISTER, VERIFY, MARK COMPLETE,
  PERSIST PROGRESS).
- `checkpoint_block()`, `verify_block()`, `export_block()` — reusable
  Phase 5/6/7 blocks.

---

## 3. Feature Flags

Two env flags exist for safe rollout and emergency rollback:

| Flag | Default | Effect when `1`/`true` |
|------|---------|------------------------|
| `LEGACY_PROMPTS` | `0` | Pipeline nodes + refinement graph fall back to the pre-v2 inline prompt strings they shipped with. Every call site reads this flag via `prompts/shared/flags.py::legacy_prompts_enabled()`. |
| `LEGACY_MCP_PLAYBOOKS` | `0` | `mcp-server/prompts/agent_loop.py` falls back to minimal legacy bodies preserved in-file for emergency rollback. |

Never edit the legacy bodies. If behaviour must change, update the v2
prompt module and let the fallbacks stay as-is.

---

## 4. Validation Harness

Location: `backend/tests/prompt_eval/`. Three modes:

### 4.1 Structural (CI)

`pytest backend/tests/prompt_eval/test_structural.py`

Runs on every commit. 81 parametrised assertions:

- Each of the 16 v2 prompts declares role, mission, constraints,
  output contract.
- Each system prompt contains `MISSION`, `HARD CONSTRAINTS`,
  `OUTPUT CONTRACT`, `REFUSAL`.
- Each JSON contract has a self-consistent schema.
- Each builder renders deterministically and reminds the model of the
  contract in the user prompt.
- A guard asserts exactly 16 surfaces are registered (stops silent
  drops).

### 4.2 Golden-diff (CI regression gate)

`pytest backend/tests/prompt_eval/test_golden.py`

Records a structural signature per prompt (role opening, mission,
constraint count, schema hash, few-shot count) and compares it against
`backend/tests/prompt_eval/golden/prompt_signatures.json`. Any
uncommitted drift fails the build.

To accept intentional changes:

```bash
cd backend && PROMPT_EVAL_UPDATE=1 pytest tests/prompt_eval/test_golden.py
```

Commit the updated JSON alongside the prompt change. Never edit the
golden file by hand.

### 4.3 Live LLM (on demand)

`PROMPT_EVAL_LIVE=1 pytest backend/tests/prompt_eval/test_live.py -s`

Runs one representative fixture per prompt through the real LLM (via
`pipeline_call_llm` / `pipeline_call_llm_json`) and asserts the
response parses against the declared `OutputContract`. Skipped by
default so CI costs zero tokens.

Use this after any non-trivial prompt change to confirm the model's
real output still matches the structural contract.

---

## 5. Authoring a New Prompt

1. Pick the right subdirectory (`analysis/`, `refinement/`, `idea/`,
   `reverse/`, `impact/`, or a new one).
2. Copy an existing prompt module as a starting point (e.g.
   `prompts/analysis/ambiguity.py`).
3. Fill in the `PromptSpec`: role, mission, constraints, output
   contract (JSON schema with `additionalProperties: false` where
   possible), refusal, and a short `few_shot` list of
   `FewShotExample` instances (`label`, `input_snippet`,
   `expected_output`).
4. Expose `NAME`, `SPEC`, and a `build(...) -> tuple[str, str]`
   function that returns `(system, user)` prompts.
5. Add the surface to `backend/tests/prompt_eval/test_structural.py`
   (import, register in `_all_prompts()`, add a sample to
   `_sample_for()` that mirrors the real call-site signature, and
   bump the count guard).
6. Wire the call site in the relevant pipeline node using the
   `legacy_prompts_enabled()` flag so an emergency rollback is always
   one env var away.
7. Run `pytest backend/tests/prompt_eval` and then
   `PROMPT_EVAL_UPDATE=1 pytest backend/tests/prompt_eval/test_golden.py`
   to record the new signature. Commit the updated golden file.

---

## 6. Canonical Build / MCP Integration

The build page (`/documents/{id}/build`) and the two agent guides
(`docs/GUIDE_CURSOR.md`, `docs/GUIDE_CLAUDE_CODE.md`) both source their
MCP snippets from `GET /api/orchestration/mcp-config`. That endpoint is
the single source of truth. If you ever need to change the MCP
command, args, or env, change the endpoint — the UI and docs will pick
it up automatically.
