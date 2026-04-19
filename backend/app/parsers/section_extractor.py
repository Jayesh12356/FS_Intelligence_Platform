"""Utility to re-extract sections from stored parsed_text.

Reuses the same heading-detection logic as the txt parser so that
GET /api/fs/{id} can return sections without needing a DB column.
"""

import re
from typing import List

from app.parsers.base import FSSection

_TXT_HEADING_PATTERNS = [
    re.compile(r"^\d+\.?\s+\S"),
    re.compile(r"^\d+\.\d+\.?\s+"),
    re.compile(r"^[A-Z][A-Z\s\-]{4,}$"),
    re.compile(r"^={3,}$"),
    re.compile(r"^-{3,}$"),
    re.compile(r"^#{1,4}\s+"),
]


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) < 2:
        return False
    if stripped.isupper() and 4 < len(stripped) <= 80 and len(stripped.split()) <= 10:
        return True
    if stripped.endswith(":") and len(stripped) < 60 and not stripped.startswith(" "):
        return True
    for pattern in _TXT_HEADING_PATTERNS:
        if pattern.match(stripped):
            return True
    return False


def _is_separator(line: str) -> bool:
    stripped = line.strip()
    return bool(re.match(r"^[=\-~*]{3,}$", stripped))


def extract_sections_from_text(text: str) -> List[FSSection]:
    """Extract structured sections from raw FS text.

    Mirrors the logic in txt_parser.parse_txt but works on an
    in-memory string rather than reading from disk.
    """
    if not text or not text.strip():
        return []

    lines = text.split("\n")
    sections: List[FSSection] = []
    current_heading = "Introduction"
    current_content: List[str] = []
    section_index = 0

    for line in lines:
        if _is_separator(line):
            continue
        if _is_heading(line):
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
            heading = line.strip().lstrip("#").strip().rstrip(":")
            current_heading = heading if heading else line.strip()
            current_content = []
        else:
            current_content.append(line)

    content_text = "\n".join(current_content).strip()
    if content_text:
        sections.append(
            FSSection(
                heading=current_heading,
                content=content_text,
                section_index=section_index,
            )
        )

    if not sections and text.strip():
        sections.append(
            FSSection(
                heading="Document Content",
                content=text.strip(),
                section_index=0,
            )
        )

    return sections


def rebuild_text_from_sections(sections: List[FSSection]) -> str:
    """Reconstruct raw text from a list of FSSection objects.

    Produces text that round-trips through extract_sections_from_text.
    """
    parts: List[str] = []
    for s in sections:
        parts.append(f"{s.heading}:")
        parts.append(s.content)
        parts.append("")  # blank line between sections
    return "\n".join(parts).rstrip("\n") + "\n"
