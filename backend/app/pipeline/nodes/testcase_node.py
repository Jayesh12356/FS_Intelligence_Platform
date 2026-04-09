"""Test case generation pipeline node (L10).

Generates test cases for each FS task based on acceptance criteria
using LLM-powered analysis.
"""

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Import call_llm at module level so it can be mocked in tests
try:
    from app.llm.client import call_llm
except ImportError:
    call_llm = None  # type: ignore


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # Preserve structure without crashing DB inserts (VARCHAR expects str)
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _coerce_steps(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_coerce_text(v) for v in value if _coerce_text(v).strip()]
    return [_coerce_text(value)]


def _extract_json_array(text: str) -> str:
    """Best-effort extraction of the first JSON array from LLM output."""
    cleaned = (text or "").strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()

    if cleaned.startswith("[") and cleaned.endswith("]"):
        return cleaned

    # Find first '[' and last ']' to tolerate leading/trailing prose.
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1].strip()
    return cleaned


async def testcase_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate test cases for each task in the pipeline state.

    For each task with acceptance criteria, uses the LLM to generate
    structured test cases (unit, integration, e2e). Falls back to
    deterministic test case generation when LLM is unavailable.

    Args:
        state: Pipeline state with 'tasks' list.

    Returns:
        Updated state with 'test_cases' list.
    """
    tasks = state.get("tasks", [])
    fs_id = state.get("fs_id", "")
    test_cases: List[Dict[str, Any]] = []
    errors: List[str] = list(state.get("errors", []))
    llm_available = call_llm is not None

    if not tasks:
        logger.info("No tasks found — skipping test case generation")
        return {**state, "test_cases": [], "errors": errors}

    if not llm_available:
        logger.info("LLM not available — generating deterministic test cases")

    for task in tasks:
        task_id = task.get("task_id", "")
        title = task.get("title", "")
        description = task.get("description", "")
        criteria = task.get("acceptance_criteria", [])
        section_idx = task.get("section_index", 0)
        section_heading = task.get("section_heading", "")

        if not criteria or not llm_available:
            # Generate a basic test case from the task description
            test_cases.append({
                "task_id": task_id,
                "title": f"Verify: {title}",
                "preconditions": "System is set up and configured",
                "steps": [
                    f"Execute: {description[:200]}",
                    "Verify the expected behavior",
                ],
                "expected_result": f"{title} works as specified",
                "test_type": "INTEGRATION",
                "section_index": section_idx,
                "section_heading": section_heading,
            })
            continue

        # Use LLM to generate test cases from acceptance criteria
        criteria_text = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(criteria))
        prompt = f"""Generate test cases for the following task.

Task: {title}
Description: {description}

Acceptance Criteria:
{criteria_text}

Generate 1-3 test cases. For each test case, return a JSON array where each element has:
- "title": short test name
- "preconditions": what must be true before the test
- "steps": array of step descriptions
- "expected_result": what should happen
- "test_type": one of "UNIT", "INTEGRATION", "E2E", or "ACCEPTANCE"

Return ONLY a JSON array, no other text."""

        try:
            response = await call_llm(prompt)
            # Parse the JSON response
            response_text = _extract_json_array(response)
            parsed = json.loads(response_text)

            if isinstance(parsed, list):
                for tc in parsed:
                    test_type = tc.get("test_type", "UNIT").upper()
                    if test_type not in ("UNIT", "INTEGRATION", "E2E", "ACCEPTANCE"):
                        test_type = "UNIT"

                    test_cases.append({
                        "task_id": task_id,
                        "title": _coerce_text(tc.get("title", f"Test for {title}")),
                        "preconditions": _coerce_text(tc.get("preconditions", "")),
                        "steps": _coerce_steps(tc.get("steps", [])),
                        "expected_result": _coerce_text(tc.get("expected_result", "")),
                        "test_type": test_type,
                        "section_index": section_idx,
                        "section_heading": section_heading,
                    })
            else:
                logger.warning("LLM returned non-list for task %s", task_id)

        except json.JSONDecodeError as exc:
            logger.warning("JSON parse error for task %s test cases: %s", task_id, exc)
            # Fallback: create basic test case per criterion
            for i, criterion in enumerate(criteria):
                test_cases.append({
                    "task_id": task_id,
                    "title": f"Verify: {criterion[:80]}",
                    "preconditions": "System is configured and running",
                    "steps": [criterion],
                    "expected_result": f"Criterion met: {criterion}",
                    "test_type": "ACCEPTANCE",
                    "section_index": section_idx,
                    "section_heading": section_heading,
                })
        except Exception as exc:
            logger.error("Test case generation failed for task %s: %s", task_id, exc)
            errors.append(f"testcase_node: {exc}")

    logger.info("Generated %d test cases for %d tasks", len(test_cases), len(tasks))

    return {**state, "test_cases": test_cases, "errors": errors}
