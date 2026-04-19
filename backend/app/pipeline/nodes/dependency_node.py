"""Dependency graph builder node — infers and validates task dependencies.

Takes state.tasks (from task_decomposition_node), uses LLM to infer
inter-task dependencies, validates no cycles exist, assigns execution
order via topological sort, and flags parallelisable tasks.
"""

import logging
from collections import defaultdict, deque
from typing import Dict, List, Set

from app.orchestration.pipeline_llm import pipeline_call_llm_json
from app.pipeline.prompts.analysis import dependency as dependency_prompt
from app.pipeline.prompts.shared.flags import legacy_prompts_enabled
from app.pipeline.state import FSAnalysisState

logger = logging.getLogger(__name__)

# ── Dependency Inference Prompt ─────────────────────────

DEPENDENCY_SYSTEM_PROMPT = """You are a build-order planner for a software project. Given a set of development tasks, you must determine the minimum set of dependencies so tasks execute in the correct order — and ONLY the minimum set.

TASK: For each task, list ONLY the task IDs it CANNOT start without. A dependency exists ONLY when:

1. DATA DEPENDENCY — Task B reads from a database table/model that task A creates. No table = B cannot run.
2. API DEPENDENCY — Task B calls an API endpoint that task A implements. No endpoint = B fails at runtime.
3. BUILD DEPENDENCY — Task B imports a module, component, or service that task A produces. Missing import = compile/import error.
4. SCHEMA DEPENDENCY — Task B relies on a data shape (interface, schema, type) that task A defines.

STRICT RULES:
- A dependency must represent a HARD blocker — B literally cannot execute without A's output.
- DO NOT add "nice to have" orderings. If B CAN run independently (even if A would make it easier), no dependency.
- DO NOT link tasks just because they are in the same feature area.
- Maximum dependency chain depth: 5. If you find yourself creating deeper chains, some dependencies are unnecessary.
- NO self-dependencies. NO circular dependencies.
- Tasks with no dependencies get an empty array [].
- Include EVERY task ID in the output, even those with zero dependencies.

COMMON PATTERNS:
- DB model -> API endpoint -> Frontend page (3-level chain, correct)
- Auth middleware -> Protected endpoints (correct)
- Two independent API endpoints for different features (NO dependency, they are parallel)

Return a JSON object mapping every task ID to its dependency list.

Example:
{
  "task-uuid-1": [],
  "task-uuid-2": ["task-uuid-1"],
  "task-uuid-3": ["task-uuid-2"],
  "task-uuid-4": []
}

Return ONLY a valid JSON object. No markdown fences, no prose outside the object."""

DEPENDENCY_USER_PROMPT = """Determine the MINIMUM dependency set for these tasks. Only add a dependency when task B literally cannot execute without task A's output.

Tasks:
{task_list}

Return a JSON object mapping EVERY task ID to its dependency array. Empty array for independent tasks."""


# ── Cycle Detection ─────────────────────────────────────


def detect_cycle(graph: Dict[str, List[str]]) -> bool:
    """Detect if a directed graph has a cycle using DFS.

    Args:
        graph: Adjacency list (node -> list of dependencies).

    Returns:
        True if a cycle exists, False otherwise.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = defaultdict(int)

    # Collect all nodes
    all_nodes: Set[str] = set(graph.keys())
    for deps in graph.values():
        all_nodes.update(deps)

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for neighbour in graph.get(node, []):
            if color[neighbour] == GRAY:
                return True  # Back edge → cycle
            if color[neighbour] == WHITE and dfs(neighbour):
                return True
        color[node] = BLACK
        return False

    for node in all_nodes:
        if color[node] == WHITE:
            if dfs(node):
                return True
    return False


# ── Topological Sort ────────────────────────────────────


def topological_sort(graph: Dict[str, List[str]], all_nodes: Set[str]) -> List[str]:
    """Topological sort via Kahn's algorithm.

    Args:
        graph: Adjacency list (node -> list of nodes it depends on).
        all_nodes: Set of all node IDs.

    Returns:
        List of node IDs in execution order (dependencies first).
    """
    # Build reverse graph (dependency -> dependents)
    in_degree: Dict[str, int] = {n: 0 for n in all_nodes}
    reverse_graph: Dict[str, List[str]] = defaultdict(list)

    for node, deps in graph.items():
        for dep in deps:
            if dep in all_nodes:
                reverse_graph[dep].append(node)
                in_degree[node] = in_degree.get(node, 0) + 1

    # Start with nodes that have no dependencies
    queue = deque([n for n in all_nodes if in_degree.get(n, 0) == 0])
    order: List[str] = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for dependent in reverse_graph.get(node, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    return order


# ── Parallel Detection ──────────────────────────────────


def find_parallel_tasks(
    tasks: List[dict],
    graph: Dict[str, List[str]],
) -> Set[str]:
    """Find tasks that can be executed in parallel.

    A task can be parallelised if it shares the same execution order level
    (same depth in dependency tree) with at least one other task.

    Args:
        tasks: List of task dicts.
        graph: Dependency adjacency list.

    Returns:
        Set of task_ids that can be parallelised.
    """
    all_ids = {t["task_id"] for t in tasks}
    order_map = topological_sort(graph, all_ids)

    # Compute depth for each task
    depth: Dict[str, int] = {}
    for task_id in order_map:
        deps = graph.get(task_id, [])
        if not deps:
            depth[task_id] = 0
        else:
            depth[task_id] = max(depth.get(d, 0) for d in deps if d in depth) + 1

    # Find tasks at the same depth level with no interdepency
    depth_groups: Dict[int, List[str]] = defaultdict(list)
    for tid, d in depth.items():
        depth_groups[d].append(tid)

    parallel_ids: Set[str] = set()
    for _depth_level, group in depth_groups.items():
        if len(group) > 1:
            parallel_ids.update(group)

    return parallel_ids


# ── LangGraph Node Function ─────────────────────────────


async def dependency_node(state: FSAnalysisState) -> FSAnalysisState:
    """LangGraph node: infer task dependencies, validate, and assign order.

    Reads state.tasks, uses LLM to infer dependencies between tasks,
    validates no cycles, assigns execution order via topological sort,
    and flags tasks that can be parallelised.
    """
    tasks = state.get("tasks", [])
    errors: List[str] = list(state.get("errors", []))

    if not tasks:
        logger.info("Dependency node: no tasks to process")
        return {**state, "tasks": [], "errors": errors}

    logger.info("Dependency node: processing %d tasks for fs_id=%s", len(tasks), state.get("fs_id", "?"))

    # Build task list description for LLM
    task_descriptions = []
    for t in tasks:
        task_descriptions.append(
            f"- **{t['task_id']}**: {t['title']}\n"
            f"  Section: §{t['section_index'] + 1} ({t['section_heading']})\n"
            f"  Tags: {', '.join(t.get('tags', []))}\n"
            f"  Description: {t.get('description', '')[:200]}"
        )

    task_list_text = "\n\n".join(task_descriptions)
    if legacy_prompts_enabled():
        system = DEPENDENCY_SYSTEM_PROMPT
        prompt = DEPENDENCY_USER_PROMPT.format(task_list=task_list_text)
    else:
        system, prompt = dependency_prompt.build(task_list_text)

    dependency_map: Dict[str, List[str]] = {}
    all_task_ids = {t["task_id"] for t in tasks}

    try:
        result = await pipeline_call_llm_json(
            prompt=prompt,
            system=system,
            temperature=0.0,
            max_tokens=2048,
            role="reasoning",
        )

        if isinstance(result, dict):
            # Validate all IDs exist
            for task_id, deps in result.items():
                if task_id not in all_task_ids:
                    continue
                valid_deps = [d for d in deps if d in all_task_ids and d != task_id]
                dependency_map[task_id] = valid_deps
        else:
            logger.warning("LLM returned non-dict for dependencies: %s", type(result))

    except Exception as exc:
        error_msg = f"Dependency inference failed: {exc}"
        logger.error(error_msg)
        errors.append(error_msg)

    # Ensure all tasks are in the map
    for t in tasks:
        if t["task_id"] not in dependency_map:
            dependency_map[t["task_id"]] = []

    # Validate no cycles
    if detect_cycle(dependency_map):
        logger.warning("Cycle detected in dependency graph — removing all inferred dependencies")
        errors.append("Cycle detected in dependency graph — dependencies cleared")
        dependency_map = {t["task_id"]: [] for t in tasks}

    # Topological sort for execution order
    order_list = topological_sort(dependency_map, all_task_ids)
    order_index = {tid: idx for idx, tid in enumerate(order_list)}

    # Find parallelisable tasks
    parallel_ids = find_parallel_tasks(tasks, dependency_map)

    # Update tasks with dependencies, order, and can_parallel
    updated_tasks: List[dict] = []
    for t in tasks:
        tid = t["task_id"]
        updated = {
            **t,
            "depends_on": dependency_map.get(tid, []),
            "order": order_index.get(tid, 0),
            "can_parallel": tid in parallel_ids,
        }
        updated_tasks.append(updated)

    # Sort tasks by order
    updated_tasks.sort(key=lambda x: x["order"])

    logger.info(
        "Dependency node complete: %d tasks, %d with dependencies, %d parallelisable",
        len(updated_tasks),
        sum(1 for t in updated_tasks if t["depends_on"]),
        sum(1 for t in updated_tasks if t["can_parallel"]),
    )

    return {
        **state,
        "tasks": updated_tasks,
        "errors": errors,
    }
