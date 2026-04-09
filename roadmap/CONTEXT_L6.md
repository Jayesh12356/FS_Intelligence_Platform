# CONTEXT_L6 — Adversarial Validation

## What This Level Builds
CrewAI two-agent debate that challenges the ambiguity detection output.
RedAgent argues requirement IS ambiguous. BlueAgent argues it IS clear.
Arbiter agent makes the final call. This improves detection precision
and is the core research differentiator.

## Stack Used
CrewAI · LangGraph (wraps CrewAI debate as a node) · LLM

## Research Angle
Compare ambiguity detection with vs without adversarial debate.
Record: precision, recall, F1. Show the debate improves precision
(fewer false positives). This goes in the thesis evaluation section.

## Build Order (5 prompts)

### Prompt 01 — CrewAI agent definitions
```
backend/app/agents/red_agent.py
  RedAgent — argues the requirement IS ambiguous
  Backstory: "You are a skeptical QA engineer who finds every
              edge case and ambiguity in requirements."
  Goal: "Find all reasons this requirement is unclear or incomplete."

backend/app/agents/blue_agent.py
  BlueAgent — argues the requirement IS clear
  Backstory: "You are a senior developer who has seen requirements
              like this many times and knows how to build from them."
  Goal: "Defend this requirement as sufficiently clear to implement."

backend/app/agents/arbiter_agent.py
  ArbiterAgent — reads both arguments, makes final verdict
  Returns: { verdict: AMBIGUOUS|CLEAR, reasoning, confidence }
```

### Prompt 02 — Debate task + crew
```
backend/app/agents/debate_crew.py
  DebateCrew:
    agents: [red_agent, blue_agent, arbiter_agent]
    tasks: [red_task, blue_task, arbiter_task]
    process: sequential (red → blue → arbiter)
  run_debate(requirement_text: str) -> DebateVerdict
    DebateVerdict: verdict, red_argument, blue_argument,
                   arbiter_reasoning, confidence
```

### Prompt 03 — LangGraph debate node
```
backend/app/pipeline/nodes/debate_node.py
  debate_node(state) -> state
  For each AmbiguityFlag in state.ambiguities:
    If flag.severity == HIGH: run DebateCrew
    If verdict == CLEAR: remove flag from state.ambiguities
    If verdict == AMBIGUOUS: keep, add debate_reasoning to flag
  Logs red_win_rate for benchmark tracking
```

### Prompt 04 — Benchmark comparison
```
backend/app/pipeline/benchmarks/debate_benchmark.py
  Run pipeline on same 3 FS documents as L3
  Before debate: precision/recall of ambiguity flags
  After debate: precision/recall of ambiguity flags
  Save comparison to data/debate_benchmark.json
  This is the key thesis evidence: debate improves precision
```

### Prompt 05 — Frontend: debate results
```
In ambiguity review UI (/documents/[id]/ambiguities):
  For HIGH severity flags: show debate transcript
    Red argument | Blue argument | Arbiter verdict
  Confidence score shown as percentage
  "Overridden by debate" badge for cleared flags
```

## Done When
- Debate runs on HIGH severity flags
- Precision improves vs L3 baseline (measured)
- Debate transcript visible in UI
- Benchmark numbers recorded for thesis

## Built
- RedAgent (backend/app/agents/red_agent.py) — skeptical QA engineer persona
- BlueAgent (backend/app/agents/blue_agent.py) — senior developer persona
- ArbiterAgent (backend/app/agents/arbiter_agent.py) — impartial architect persona
- LLM config bridge (backend/app/agents/llm_config.py) — maps project settings to CrewAI LLM
- DebateCrew (backend/app/agents/debate_crew.py) — sequential Red→Blue→Arbiter orchestration
- DebateVerdict model (backend/app/pipeline/state.py) — verdict, arguments, reasoning, confidence
- debate_node (backend/app/pipeline/nodes/debate_node.py) — LangGraph node wrapping CrewAI debate
- Pipeline graph updated (9 nodes: parse→ambiguity→debate→contradiction→edge_case→quality→task→dependency→traceability)
- DebateResultDB table (backend/app/db/models.py) — persists debate results with FK to documents
- DebateResultSchema (backend/app/models/schemas.py) — API response schema
- GET /api/fs/{id}/debate-results endpoint (backend/app/api/analysis_router.py)
- Debate results persisted in analyze_document endpoint
- Benchmark script (backend/app/pipeline/benchmarks/debate_benchmark.py) — precision/recall comparison
- Frontend debate transcript UI (frontend/src/app/documents/[id]/ambiguities/page.tsx)
  - Red/Blue/Arbiter argument panels with expand/collapse
  - Confidence bar visualization
  - "Overridden by debate" section for cleared flags
  - "Debate Confirmed" badge on surviving HIGH flags
  - Summary banner with confirmed/cleared counts
- Frontend API types + getDebateResults function (frontend/src/lib/api.ts)
- crewai added to requirements.txt
- 25 new tests (120 total): DebateVerdict model, debate node logic, output parsing, benchmark math, API endpoints

## Status: ✅ COMPLETE
