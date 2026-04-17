"""FS refinement pipeline — improve low-quality FS text using detected issues.

Pipeline:
  issues_collector_node -> suggestion_node -> rewriter_node -> validation_node -> END
"""

from __future__ import annotations

import difflib
import logging
from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AmbiguityFlagDB, ContradictionDB, EdgeCaseGapDB, FSDocument
from app.llm.client import LLMError
from app.orchestration.pipeline_llm import pipeline_call_llm, pipeline_call_llm_json
from app.parsers.chunker import chunk_text_into_sections

logger = logging.getLogger(__name__)


class RefinementIssue(TypedDict, total=False):
    issue_id: str
    issue_type: str
    issue: str
    original_text: str
    section_heading: str
    suggested_fix: str


class RefinementState(TypedDict, total=False):
    document_id: str
    original_text: str
    original_score: float
    refined_score: float
    accepted: bool
    issues: list[RefinementIssue]
    suggestions: list[RefinementIssue]
    refined_text: str
    diff: list[dict[str, Any]]
    changes_made: int
    errors: list[str]


SUGGESTION_SYSTEM = """You are a requirements engineer fixing defects in Functional Specifications. For each issue, produce a single replacement that RESOLVES the issue while preserving the original intent.

REPLACEMENT RULES:
1. The fix must DIRECTLY address the flagged issue — ambiguity gets specific numbers/conditions, contradiction gets reconciled, missing edge case gets explicit handling.
2. Use formal FS language: "The system shall..." for requirements. Be specific and measurable (response times in ms, retention periods in days, field lengths in characters).
3. The replacement must be a DROP-IN substitution — same scope, same paragraph size (±2 sentences). Do NOT expand a single sentence into a full page.
4. Do NOT add requirements that were not implied by the original text. Fix what is broken, nothing more.
5. Preserve the original terminology, actor names, and system references.

Return ONLY a JSON object: {"suggested_fix": "your replacement text"}
No markdown, no explanation, no extra keys."""


REWRITER_SYSTEM = """You are a document editor applying approved fixes to a Functional Specification. Your job is MECHANICAL — apply each suggestion to the exact location in the text and change nothing else.

RULES:
1. For each suggestion, find the original text in the document and replace it with the suggested fix.
2. Append the token [REFINED] at the end of every modified line so reviewers can spot changes.
3. PRESERVE all headings, section numbers, bullet formatting, and paragraph structure.
4. DO NOT rephrase, reorganize, or improve text that has no suggestion — only touch lines with an explicit fix.
5. If a suggestion cannot be applied (original text not found), skip it silently.
6. Return the COMPLETE document text with fixes applied. Do not truncate or summarize.

Return plain text only. No markdown fences, no JSON."""


async def issues_collector_node(state: RefinementState, db: AsyncSession) -> RefinementState:
    doc_id = UUID(state["document_id"])
    doc_result = await db.execute(select(FSDocument).where(FSDocument.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        return {**state, "errors": [*state.get("errors", []), "Document not found"]}

    original_text = (doc.parsed_text or doc.original_text or "").strip()
    if not original_text:
        return {**state, "errors": [*state.get("errors", []), "Document has no text to refine"]}

    amb_rows = (
        await db.execute(select(AmbiguityFlagDB).where(AmbiguityFlagDB.fs_id == doc_id, AmbiguityFlagDB.resolved.is_(False)))
    ).scalars().all()
    con_rows = (
        await db.execute(select(ContradictionDB).where(ContradictionDB.fs_id == doc_id, ContradictionDB.resolved.is_(False)))
    ).scalars().all()
    edge_rows = (
        await db.execute(select(EdgeCaseGapDB).where(EdgeCaseGapDB.fs_id == doc_id, EdgeCaseGapDB.resolved.is_(False)))
    ).scalars().all()

    issues: list[RefinementIssue] = []
    for row in amb_rows:
        issues.append(
            {
                "issue_id": str(row.id),
                "issue_type": "ambiguity",
                "issue": row.reason,
                "original_text": row.flagged_text,
                "section_heading": row.section_heading,
            }
        )
    for row in con_rows:
        issues.append(
            {
                "issue_id": str(row.id),
                "issue_type": "contradiction",
                "issue": row.description,
                "original_text": row.suggested_resolution or row.description,
                "section_heading": f"{row.section_a_heading} vs {row.section_b_heading}",
            }
        )
    for row in edge_rows:
        issues.append(
            {
                "issue_id": str(row.id),
                "issue_type": "edge_case",
                "issue": row.scenario_description,
                "original_text": row.suggested_addition or row.scenario_description,
                "section_heading": row.section_heading,
            }
        )

    sections = chunk_text_into_sections(original_text)
    ambiguity_penalty = min(len(amb_rows) * 3.0, 15.0)
    contradiction_penalty = min(len(con_rows) * 1.5, 10.0)
    edge_penalty = min(len(edge_rows) * 2.0, 20.0)
    completeness = max(0.0, 100.0 - ambiguity_penalty - edge_penalty)
    clarity = max(0.0, 100.0 - min(len(amb_rows) * 2.5, 30.0))
    consistency = max(0.0, 100.0 - contradiction_penalty)
    original_overall = round((completeness + clarity + consistency) / 3.0, 1)

    return {
        **state,
        "original_text": original_text,
        "issues": issues,
        "original_score": float(original_overall),
    }


async def suggestion_node(state: RefinementState) -> RefinementState:
    issues = state.get("issues", [])
    if not issues:
        return {**state, "suggestions": []}

    suggestions: list[RefinementIssue] = []
    for issue in issues:
        prompt = (
            f"Issue Type: {issue.get('issue_type')}\n"
            f"Section: {issue.get('section_heading')}\n"
            f"Defect: {issue.get('issue')}\n"
            f"Original Text: {issue.get('original_text')}\n\n"
            "Write one replacement that fixes the defect. Return JSON: {\"suggested_fix\": \"...\"}"
        )
        try:
            res = await pipeline_call_llm_json(
                prompt=prompt,
                system=SUGGESTION_SYSTEM,
                temperature=0.0,
                max_tokens=220,
                role="longcontext",
            )
            suggested_fix = str((res or {}).get("suggested_fix") or "").strip()
            if not suggested_fix:
                suggested_fix = f"{issue.get('original_text', '')} [REFINED]"
        except LLMError:
            raise
        except (TypeError, ValueError, KeyError) as exc:
            logger.warning(
                "Suggestion LLM response malformed for issue %s: %s",
                issue.get("issue_id"), exc,
            )
            suggested_fix = f"{issue.get('original_text', '')} [REFINED]"

        suggestions.append({**issue, "suggested_fix": suggested_fix})

    return {**state, "suggestions": suggestions}


async def rewriter_node(state: RefinementState) -> RefinementState:
    original_text = state.get("original_text", "")
    suggestions = state.get("suggestions", [])
    if not original_text:
        return state

    if not suggestions:
        return {**state, "refined_text": original_text, "changes_made": 0, "diff": []}

    suggestion_lines = "\n".join(
        f"FIX {i+1}: Find \"{s.get('original_text')}\" → Replace with \"{s.get('suggested_fix')}\""
        for i, s in enumerate(suggestions)
    )
    prompt = (
        "DOCUMENT TO EDIT:\n"
        f"{original_text}\n\n"
        f"FIXES TO APPLY ({len(suggestions)} total):\n"
        f"{suggestion_lines}\n\n"
        "Apply each fix at its exact location. Append [REFINED] to every modified line. Return the complete document."
    )

    refined_text = ""
    try:
        refined_text = (
            await pipeline_call_llm(
                prompt=prompt,
                system=REWRITER_SYSTEM,
                temperature=0.0,
                max_tokens=8192,
                role="longcontext",
            )
        ).strip()
    except LLMError:
        raise
    except (TypeError, ValueError) as exc:
        logger.warning("Rewriter LLM returned unexpected shape: %s", exc)
        refined_text = original_text

    if not refined_text:
        refined_text = original_text

    # Deterministic fallback touches lines when LLM misses visible marks.
    if "[REFINED]" not in refined_text:
        for s in suggestions:
            original = str(s.get("original_text") or "").strip()
            fix = str(s.get("suggested_fix") or "").strip()
            if original and fix and original in refined_text:
                refined_text = refined_text.replace(original, f"{fix} [REFINED]", 1)

    diff_lines = list(difflib.unified_diff(original_text.splitlines(), refined_text.splitlines(), lineterm=""))
    diff = [{"line": line} for line in diff_lines]
    changes_made = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))

    return {**state, "refined_text": refined_text, "diff": diff, "changes_made": changes_made}


async def validation_node(state: RefinementState) -> RefinementState:
    original_score = float(state.get("original_score", 0.0))
    refined_text = state.get("refined_text", "")
    original_text = state.get("original_text", "")
    suggestions = state.get("suggestions", [])

    if not refined_text:
        return {**state, "accepted": False, "refined_score": original_score, "refined_text": original_text}

    remaining = 0
    for s in suggestions:
        original_issue_text = str(s.get("original_text") or "").strip()
        if original_issue_text and original_issue_text in refined_text:
            remaining += 1

    total = max(len(suggestions), 1)
    resolved_ratio = 1.0 - (remaining / total)
    uplift = round(resolved_ratio * 15.0, 1)
    refined_score = min(100.0, round(original_score + uplift, 1))
    accepted = refined_score >= original_score

    if not accepted:
        return {
            **state,
            "accepted": False,
            "refined_score": original_score,
            "refined_text": original_text,
            "diff": [],
            "changes_made": 0,
        }

    return {**state, "accepted": True, "refined_score": refined_score}


TARGETED_REWRITER_SYSTEM = """You perform surgical edits on an FS document. For each issue, replace ONLY the affected sentence or paragraph — touch nothing else. Append [REFINED] to every modified line. Return the full document with targeted fixes applied."""


def _normalize_ws(text: str) -> str:
    """Collapse all whitespace to single spaces for fuzzy matching."""
    return " ".join(text.split())


def _fuzzy_replace(haystack: str, needle: str, replacement: str) -> tuple[str, bool]:
    """Try exact match first, then fall back to normalized-whitespace matching."""
    if needle in haystack:
        return haystack.replace(needle, replacement, 1), True

    norm_needle = _normalize_ws(needle)
    if len(norm_needle) < 10:
        return haystack, False

    lines = haystack.split("\n")
    best_start = -1
    best_end = -1
    best_score = 0.0

    for i in range(len(lines)):
        for j in range(i + 1, min(i + 8, len(lines) + 1)):
            window = "\n".join(lines[i:j])
            norm_window = _normalize_ws(window)
            seq = difflib.SequenceMatcher(None, norm_needle, norm_window)
            ratio = seq.ratio()
            if ratio > best_score and ratio > 0.75:
                best_score = ratio
                best_start = i
                best_end = j

    if best_start >= 0:
        lines[best_start:best_end] = [replacement]
        return "\n".join(lines), True

    return haystack, False


async def targeted_rewriter_node(state: RefinementState) -> RefinementState:
    """Surgical mode: only fix the specific paragraphs that have issues."""
    original_text = state.get("original_text", "")
    suggestions = state.get("suggestions", [])
    if not original_text or not suggestions:
        return {**state, "refined_text": original_text, "changes_made": 0, "diff": []}

    refined_text = original_text
    changes = 0
    for s in suggestions:
        original_frag = str(s.get("original_text") or "").strip()
        fix = str(s.get("suggested_fix") or "").strip()
        if not original_frag or not fix:
            continue
        refined_text, applied = _fuzzy_replace(refined_text, original_frag, f"{fix} [REFINED]")
        if applied:
            changes += 1

    diff_lines = list(difflib.unified_diff(
        original_text.splitlines(), refined_text.splitlines(), lineterm=""
    ))
    diff = [{"line": line} for line in diff_lines]
    return {**state, "refined_text": refined_text, "diff": diff, "changes_made": changes}


async def run_refinement_pipeline(
    document_id: str, db: AsyncSession, mode: str = "auto"
) -> RefinementState:
    state: RefinementState = {"document_id": document_id, "errors": []}
    state = await issues_collector_node(state, db)
    if state.get("errors"):
        return state

    use_targeted = False
    if mode == "targeted":
        use_targeted = True
    elif mode == "auto":
        use_targeted = len(state.get("issues", [])) <= 5
    # mode == "full" -> use_targeted stays False

    state = await suggestion_node(state)

    if use_targeted:
        logger.info("Refinement using targeted mode (%d issues)", len(state.get("issues", [])))
        state = await targeted_rewriter_node(state)
    else:
        logger.info("Refinement using full rewrite mode (%d issues)", len(state.get("issues", [])))
        state = await rewriter_node(state)

    state = await validation_node(state)
    return state

