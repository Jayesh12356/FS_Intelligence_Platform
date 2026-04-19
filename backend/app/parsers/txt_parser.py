"""Plain-text parser — extracts sections from .txt files.

Uses simple line-based heuristics to detect section boundaries:
blank-line separated blocks, lines ending with colons, ALL CAPS lines, etc.
"""

import logging
import re
from pathlib import Path
from typing import List

from app.parsers.base import FSSection, ParsedFS

logger = logging.getLogger(__name__)

# Patterns that suggest a heading in plain text
_TXT_HEADING_PATTERNS = [
    re.compile(r"^\d+\.?\s+\S"),  # "1. Introduction"
    re.compile(r"^\d+\.\d+\.?\s+"),  # "1.1 Sub-section"
    re.compile(r"^[A-Z][A-Z\s\-]{4,}$"),  # "OVERVIEW"
    re.compile(r"^={3,}$"),  # "===" separator
    re.compile(r"^-{3,}$"),  # "---" separator
    re.compile(r"^#{1,4}\s+"),  # Markdown-style headings
]


def _is_heading(line: str) -> bool:
    """Detect if a line is likely a heading."""
    stripped = line.strip()
    if not stripped or len(stripped) < 2:
        return False

    # ALL CAPS line (5+ chars, not too long)
    if stripped.isupper() and 4 < len(stripped) <= 80 and len(stripped.split()) <= 10:
        return True

    # Line ending with colon and short (likely a heading)
    if stripped.endswith(":") and len(stripped) < 60 and not stripped.startswith(" "):
        return True

    for pattern in _TXT_HEADING_PATTERNS:
        if pattern.match(stripped):
            return True

    return False


def _is_separator(line: str) -> bool:
    """Check if line is a visual separator (===, ---, etc.)."""
    stripped = line.strip()
    return bool(re.match(r"^[=\-~*]{3,}$", stripped))


def parse_txt(filepath: str) -> ParsedFS:
    """Parse a plain-text file into structured sections.

    Args:
        filepath: Path to the TXT file on disk.

    Returns:
        ParsedFS with raw text and detected sections.

    Raises:
        FileNotFoundError: If the file doesn't exist.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"TXT file not found: {filepath}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw_text = path.read_text(encoding="latin-1")

    if not raw_text.strip():
        return ParsedFS(
            raw_text="",
            sections=[],
            metadata={"parser": "txt", "characters": 0},
        )

    lines = raw_text.split("\n")
    sections: List[FSSection] = []
    current_heading = "Introduction"
    current_content: List[str] = []
    section_index = 0

    for line in lines:
        if _is_separator(line):
            continue  # Skip visual separators

        if _is_heading(line):
            # Save previous section
            content_text = "\n".join(current_content).strip()
            if content_text:
                sections.append(
                    FSSection(
                        heading=current_heading,
                        content=content_text,
                        section_index=section_index,
                    )
                )
                section_index += 1
            # Clean heading (remove markdown #, trailing :)
            heading = line.strip().lstrip("#").strip().rstrip(":")
            current_heading = heading if heading else line.strip()
            current_content = []
        else:
            current_content.append(line)

    # Save the last section
    content_text = "\n".join(current_content).strip()
    if content_text:
        sections.append(
            FSSection(
                heading=current_heading,
                content=content_text,
                section_index=section_index,
            )
        )

    # Fallback
    if not sections and raw_text.strip():
        sections.append(
            FSSection(
                heading="Document Content",
                content=raw_text.strip(),
                section_index=0,
            )
        )

    logger.info("Parsed TXT %s: %d lines, %d sections, %d chars", filepath, len(lines), len(sections), len(raw_text))

    return ParsedFS(
        raw_text=raw_text,
        sections=sections,
        metadata={
            "lines": len(lines),
            "parser": "txt",
            "characters": len(raw_text),
        },
    )
