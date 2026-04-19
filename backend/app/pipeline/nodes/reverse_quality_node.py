"""Reverse FS quality checker node — assesses generated FS quality (L8).

Evaluates:
  - Coverage: % of codebase entities documented in the generated FS
  - Gaps: undocumented areas / files with no docstrings
  - Confidence: overall confidence in the generated FS quality
"""

import logging
from typing import List

from app.pipeline.state import GeneratedFSReport, ReverseGenState

logger = logging.getLogger(__name__)


def compute_coverage(snapshot: dict, generated_sections: List[dict]) -> GeneratedFSReport:
    """Compute quality metrics for the generated FS.

    Args:
        snapshot: CodebaseSnapshot-like dict.
        generated_sections: Generated FS sections.

    Returns:
        GeneratedFSReport with coverage, gaps, and confidence.
    """
    files = snapshot.get("files", [])
    parser_stats = snapshot.get("parser_stats", {}) or {}

    # Count total entities and documented entities
    total_entities = 0
    documented_entities = 0
    undocumented_files: List[str] = []
    gaps: List[str] = []
    confidence_reasons: List[str] = []

    for f in files:
        entities = f.get("entities", [])
        total_entities += max(len(entities), 1)  # At least 1 per file

        has_docs = f.get("has_docstrings", False)
        file_entities_with_docs = sum(1 for e in entities if e.get("docstring"))

        if entities:
            documented_entities += file_entities_with_docs
        elif has_docs:
            documented_entities += 1

        # Track undocumented files
        if not has_docs and entities:
            undocumented_files.append(f.get("path", "unknown"))
            gaps.append(f"File '{f.get('path', '?')}' has {len(entities)} entities but no docstrings")

        # Check for functions without docstrings
        undocumented_fns = [e for e in entities if not e.get("docstring")]
        if len(undocumented_fns) > 3:
            gaps.append(f"File '{f.get('path', '?')}' has {len(undocumented_fns)} undocumented functions/classes")

    # Coverage: proportion of entities with docstrings
    coverage = documented_entities / max(total_entities, 1)

    # Also factor in how many sections were generated
    section_count = len(generated_sections)
    # More sections = more coverage of flows
    flow_coverage = min(section_count / max(len(files), 1), 1.0)

    # Combined coverage (weighted)
    combined_coverage = (coverage * 0.6) + (flow_coverage * 0.4)

    # Confidence: based on coverage + quality indicators
    # High if good docstrings + many sections; low if sparse
    confidence = combined_coverage * 0.8

    # Boost confidence if most sections have real content
    sections_with_content = sum(
        1
        for s in generated_sections
        if len(s.get("content", "")) > 100 and "[Generation failed" not in s.get("content", "")
    )
    if generated_sections:
        section_quality = sections_with_content / len(generated_sections)
        confidence = confidence * 0.5 + section_quality * 0.5
    else:
        confidence_reasons.append("No FS sections were generated.")

    # Clamp
    coverage = round(min(max(combined_coverage, 0.0), 1.0), 2)
    confidence = round(min(max(confidence, 0.0), 1.0), 2)

    # Add gaps for sections that failed to generate
    for s in generated_sections:
        if "[Generation failed" in s.get("content", ""):
            gaps.append(f"Section '{s.get('heading', '?')}' failed to generate")

    if parser_stats:
        skipped = int(parser_stats.get("skipped_files", 0))
        parsed = int(parser_stats.get("parsed_files", 0))
        if skipped > parsed:
            confidence_reasons.append(f"Parser skipped many files ({skipped}) compared to parsed files ({parsed}).")

    if coverage >= 0.75:
        confidence_reasons.append("Good source coverage from documented entities.")
    elif coverage >= 0.5:
        confidence_reasons.append("Moderate source coverage; some detail may be missing.")
    else:
        confidence_reasons.append("Low source coverage; generated FS may be incomplete.")

    return GeneratedFSReport(
        coverage=coverage,
        gaps=gaps,
        confidence=confidence,
        total_entities=total_entities,
        documented_entities=documented_entities,
        undocumented_files=undocumented_files,
        confidence_reasons=confidence_reasons,
    )


# ── LangGraph Node Function ─────────────────────────────


async def reverse_quality_node(state: ReverseGenState) -> ReverseGenState:
    """LangGraph node: assess quality of generated FS.

    Computes coverage, identifies gaps, and assigns confidence score.
    """
    snapshot = state.get("snapshot", {})
    generated_sections = state.get("generated_sections", [])
    generation_stats = state.get("generation_stats", {}) or {}
    errors: List[str] = list(state.get("errors", []))

    logger.info(
        "Reverse quality node: checking quality for upload=%s",
        state.get("code_upload_id", "?"),
    )

    try:
        report = compute_coverage(snapshot, generated_sections)
        report_dict = report.model_dump()
        report_dict["generation_stats"] = generation_stats

        logger.info(
            "Quality check complete: coverage=%.0f%%, confidence=%.0f%%, %d gaps, %d undocumented files",
            report.coverage * 100,
            report.confidence * 100,
            len(report.gaps),
            len(report.undocumented_files),
        )
    except Exception as exc:
        error_msg = f"Quality check failed: {exc}"
        logger.error(error_msg)
        errors.append(error_msg)
        report_dict = GeneratedFSReport().model_dump()

    return {
        **state,
        "report": report_dict,
        "errors": errors,
    }
