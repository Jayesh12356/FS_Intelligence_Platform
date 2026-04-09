"""Version diff node — computes text diff between FS document versions (L7).

Compares old and new parsed sections to identify:
  - ADDED sections (new in v_new)
  - MODIFIED sections (content changed)
  - DELETED sections (removed in v_new)

Uses difflib for accurate text comparison.
"""

import difflib
import logging
from typing import List, Optional

from app.pipeline.state import ChangeType, FSChange, FSImpactState

logger = logging.getLogger(__name__)


def compute_section_diff(
    old_sections: List[dict],
    new_sections: List[dict],
) -> List[FSChange]:
    """Compute diff between old and new section lists.

    Matches sections by heading (case-insensitive). If headings don't
    match, falls back to index-based comparison for ordered sections.

    Args:
        old_sections: List of section dicts from previous version.
        new_sections: List of section dicts from new version.

    Returns:
        List of FSChange objects describing the differences.
    """
    changes: List[FSChange] = []

    # Build lookup maps by heading (lowercase)
    old_by_heading: dict[str, dict] = {}
    for s in old_sections:
        heading = s.get("heading", "").strip()
        key = heading.lower()
        old_by_heading[key] = s

    new_by_heading: dict[str, dict] = {}
    for s in new_sections:
        heading = s.get("heading", "").strip()
        key = heading.lower()
        new_by_heading[key] = s

    # Track processed headings
    processed_old: set[str] = set()

    # Check new sections against old
    for key, new_sec in new_by_heading.items():
        heading = new_sec.get("heading", "")
        new_content = new_sec.get("content", "").strip()
        section_index = new_sec.get("section_index", 0)

        if key in old_by_heading:
            # Section exists in both — check for modification
            old_sec = old_by_heading[key]
            old_content = old_sec.get("content", "").strip()
            processed_old.add(key)

            if old_content != new_content:
                # Content changed — compute similarity ratio
                ratio = difflib.SequenceMatcher(
                    None, old_content, new_content
                ).ratio()

                if ratio < 0.95:  # Only flag if meaningfully different
                    changes.append(FSChange(
                        change_type=ChangeType.MODIFIED,
                        section_id=f"section_{section_index}",
                        section_heading=heading,
                        section_index=section_index,
                        old_text=old_content,
                        new_text=new_content,
                    ))
        else:
            # New section — ADDED
            changes.append(FSChange(
                change_type=ChangeType.ADDED,
                section_id=f"section_{section_index}",
                section_heading=heading,
                section_index=section_index,
                old_text=None,
                new_text=new_content,
            ))

    # Check for deleted sections (in old but not in new)
    for key, old_sec in old_by_heading.items():
        if key not in processed_old and key not in new_by_heading:
            heading = old_sec.get("heading", "")
            old_content = old_sec.get("content", "").strip()
            section_index = old_sec.get("section_index", 0)

            changes.append(FSChange(
                change_type=ChangeType.DELETED,
                section_id=f"section_{section_index}",
                section_heading=heading,
                section_index=section_index,
                old_text=old_content,
                new_text=None,
            ))

    # Sort by section_index for consistent ordering
    changes.sort(key=lambda c: c.section_index)

    return changes


def generate_diff_summary(changes: List[FSChange]) -> str:
    """Generate a human-readable summary of changes.

    Args:
        changes: List of FSChange objects.

    Returns:
        Multi-line summary string.
    """
    if not changes:
        return "No changes detected."

    added = sum(1 for c in changes if c.change_type == ChangeType.ADDED)
    modified = sum(1 for c in changes if c.change_type == ChangeType.MODIFIED)
    deleted = sum(1 for c in changes if c.change_type == ChangeType.DELETED)

    lines = [f"{len(changes)} change(s) detected: {added} added, {modified} modified, {deleted} deleted."]

    for change in changes:
        if change.change_type == ChangeType.ADDED:
            lines.append(f"  + ADDED: {change.section_heading}")
        elif change.change_type == ChangeType.MODIFIED:
            lines.append(f"  ~ MODIFIED: {change.section_heading}")
        elif change.change_type == ChangeType.DELETED:
            lines.append(f"  - DELETED: {change.section_heading}")

    return "\n".join(lines)


# ── LangGraph Node Function ─────────────────────────────


async def version_node(state: FSImpactState) -> FSImpactState:
    """LangGraph node: compute diff between old and new FS versions.

    Reads state.old_sections and state.new_sections,
    computes the diff, and populates state.fs_changes.
    """
    old_sections = state.get("old_sections", [])
    new_sections = state.get("new_sections", [])
    errors: List[str] = list(state.get("errors", []))

    logger.info(
        "Version node: comparing %d old sections with %d new sections for fs_id=%s",
        len(old_sections), len(new_sections), state.get("fs_id", "?"),
    )

    try:
        changes = compute_section_diff(old_sections, new_sections)
        change_dicts = [c.model_dump() for c in changes]

        logger.info(
            "Version node: %d changes detected (%d added, %d modified, %d deleted)",
            len(changes),
            sum(1 for c in changes if c.change_type == ChangeType.ADDED),
            sum(1 for c in changes if c.change_type == ChangeType.MODIFIED),
            sum(1 for c in changes if c.change_type == ChangeType.DELETED),
        )
    except Exception as exc:
        error_msg = f"Version diff computation failed: {exc}"
        logger.error(error_msg)
        errors.append(error_msg)
        change_dicts = []

    return {
        **state,
        "fs_changes": change_dicts,
        "errors": errors,
    }
