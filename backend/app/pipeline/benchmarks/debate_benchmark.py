"""Debate benchmark — compares ambiguity detection with and without adversarial debate.

Runs the pipeline on sample FS documents and measures:
  - Before debate: precision/recall of ambiguity flags
  - After debate: precision/recall of ambiguity flags
  - Saves comparison to data/debate_benchmark.json

This is the key thesis evidence: debate improves precision
(fewer false positives) while maintaining recall.

Usage:
    python -m app.pipeline.benchmarks.debate_benchmark
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ── Default Benchmark Sections ──────────────────────────
# These simulate FS sections with known ambiguity ground truth.
# Each section has a "ground_truth" key: list of texts that are truly ambiguous.

BENCHMARK_SECTIONS: List[Dict[str, Any]] = [
    {
        "heading": "User Authentication",
        "content": (
            "The system shall authenticate users via username and password. "
            "Passwords must meet appropriate security standards. "
            "Session tokens should expire after a reasonable period. "
            "Failed login attempts must be handled properly."
        ),
        "section_index": 0,
        "ground_truth_ambiguous": [
            "appropriate security standards",
            "reasonable period",
            "handled properly",
        ],
    },
    {
        "heading": "Payment Processing",
        "content": (
            "The system shall process payments via Stripe API. "
            "All transactions over $10,000 require manual approval from a supervisor. "
            "The payment confirmation page must display the transaction ID, amount, "
            "and timestamp in ISO 8601 format. "
            "Refunds must be processed within 24 hours of request submission."
        ),
        "section_index": 1,
        "ground_truth_ambiguous": [],  # This section is clear
    },
    {
        "heading": "Data Export",
        "content": (
            "Users should be able to export their data in various formats. "
            "The export process must be fast enough for large datasets. "
            "Exported files should include all relevant information. "
            "The system shall support scheduled exports as needed."
        ),
        "section_index": 2,
        "ground_truth_ambiguous": [
            "various formats",
            "fast enough",
            "relevant information",
            "as needed",
        ],
    },
]


def _compute_precision_recall(
    detected_flags: List[Dict[str, Any]],
    ground_truth_sections: List[Dict[str, Any]],
) -> Dict[str, float]:
    """Compute precision and recall of ambiguity detection.

    Args:
        detected_flags: List of ambiguity flag dicts with section_index and flagged_text.
        ground_truth_sections: Benchmark sections with ground_truth_ambiguous lists.

    Returns:
        Dict with precision, recall, and f1 scores.
    """
    # Build ground truth set
    gt_count = 0
    gt_texts_by_section: Dict[int, List[str]] = {}
    for section in ground_truth_sections:
        idx = section["section_index"]
        gt_texts = section.get("ground_truth_ambiguous", [])
        gt_texts_by_section[idx] = [t.lower() for t in gt_texts]
        gt_count += len(gt_texts)

    if gt_count == 0 and len(detected_flags) == 0:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    # Count true positives (detected flag matches a ground truth ambiguity)
    true_positives = 0
    for flag in detected_flags:
        section_idx = flag.get("section_index", -1)
        flagged_text = flag.get("flagged_text", "").lower()
        gt_texts = gt_texts_by_section.get(section_idx, [])
        for gt in gt_texts:
            if gt in flagged_text or flagged_text in gt:
                true_positives += 1
                break

    total_detected = len(detected_flags)
    precision = true_positives / total_detected if total_detected > 0 else 0.0
    recall = true_positives / gt_count if gt_count > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


async def run_debate_benchmark(
    sections: List[Dict[str, Any]] | None = None,
    output_path: str = "data/debate_benchmark.json",
) -> Dict[str, Any]:
    """Run the benchmark comparing ambiguity detection with/without debate.

    1. Run ambiguity detection only (L3 baseline)
    2. Run debate on HIGH severity flags (L6)
    3. Compare precision/recall before vs after debate
    4. Save results to JSON

    Args:
        sections: Custom benchmark sections (uses defaults if None).
        output_path: Path to save results JSON.

    Returns:
        Benchmark comparison results.
    """
    from app.pipeline.nodes.ambiguity_node import detect_ambiguities_in_section
    from app.agents.debate_crew import run_debate

    benchmark_sections = sections or BENCHMARK_SECTIONS

    logger.info("Starting debate benchmark with %d sections", len(benchmark_sections))

    # ── Phase 1: Run ambiguity detection (L3 baseline) ──
    all_flags_before: List[Dict[str, Any]] = []
    for section in benchmark_sections:
        flags = await detect_ambiguities_in_section(
            heading=section["heading"],
            content=section["content"],
            section_index=section["section_index"],
        )
        for flag in flags:
            all_flags_before.append(flag.model_dump())

    before_metrics = _compute_precision_recall(all_flags_before, benchmark_sections)
    high_flags = [f for f in all_flags_before if f.get("severity") == "HIGH"]

    logger.info(
        "Before debate: %d flags (%d HIGH), precision=%.2f, recall=%.2f, f1=%.2f",
        len(all_flags_before),
        len(high_flags),
        before_metrics["precision"],
        before_metrics["recall"],
        before_metrics["f1"],
    )

    # ── Phase 2: Run debate on HIGH severity flags ──
    debate_verdicts: List[Dict[str, Any]] = []
    cleared_indices: List[int] = []

    for i, flag in enumerate(high_flags):
        verdict = await run_debate(
            requirement_text=flag.get("flagged_text", ""),
            flag_reason=flag.get("reason", ""),
            section_heading=flag.get("section_heading", ""),
        )
        verdict_dict = {
            "flagged_text": flag.get("flagged_text", ""),
            "verdict": verdict.verdict,
            "confidence": verdict.confidence,
        }
        debate_verdicts.append(verdict_dict)

        if verdict.verdict == "CLEAR":
            cleared_indices.append(i)

    # Remove cleared flags
    cleared_flags_set = {high_flags[i].get("flagged_text", "") for i in cleared_indices}
    all_flags_after = [
        f for f in all_flags_before
        if f.get("flagged_text", "") not in cleared_flags_set
    ]

    after_metrics = _compute_precision_recall(all_flags_after, benchmark_sections)

    logger.info(
        "After debate: %d flags (removed %d), precision=%.2f, recall=%.2f, f1=%.2f",
        len(all_flags_after),
        len(cleared_indices),
        after_metrics["precision"],
        after_metrics["recall"],
        after_metrics["f1"],
    )

    # ── Phase 3: Compile and save results ──
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sections_count": len(benchmark_sections),
        "before_debate": {
            "total_flags": len(all_flags_before),
            "high_severity_flags": len(high_flags),
            **before_metrics,
        },
        "after_debate": {
            "total_flags": len(all_flags_after),
            "cleared_by_debate": len(cleared_indices),
            **after_metrics,
        },
        "improvement": {
            "precision_delta": round(after_metrics["precision"] - before_metrics["precision"], 4),
            "recall_delta": round(after_metrics["recall"] - before_metrics["recall"], 4),
            "f1_delta": round(after_metrics["f1"] - before_metrics["f1"], 4),
            "false_positives_removed": len(cleared_indices),
        },
        "debate_verdicts": debate_verdicts,
    }

    # Save to file
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logger.info("Benchmark results saved to %s", output_path)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_debate_benchmark())
