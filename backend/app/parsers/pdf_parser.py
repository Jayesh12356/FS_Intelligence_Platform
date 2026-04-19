"""PDF parser — extracts structured sections from PDF documents.

Uses pypdf for text extraction. Applies heuristic heading detection
to identify section boundaries (ALL CAPS lines, numbered headings, etc.).
"""

import logging
import re
from pathlib import Path
from typing import List

from pypdf import PdfReader

from app.parsers.base import FSSection, ParsedFS

logger = logging.getLogger(__name__)

# Patterns that indicate a heading line
_HEADING_PATTERNS = [
    re.compile(r"^\d+\.?\s+[A-Z]"),  # "1. Introduction" or "1 OVERVIEW"
    re.compile(r"^\d+\.\d+\.?\s+"),  # "1.1 Sub-section"
    re.compile(r"^[A-Z][A-Z\s\-]{4,}$"),  # "INTRODUCTION" (all caps, 5+ chars)
    re.compile(r"^(Section|Chapter|Part)\s+", re.IGNORECASE),  # "Section 3"
    re.compile(r"^(Appendix|Annex)\s+", re.IGNORECASE),  # "Appendix A"
]


def _is_heading(line: str) -> bool:
    """Detect if a line is likely a section heading."""
    stripped = line.strip()
    if not stripped or len(stripped) < 3:
        return False
    # Short ALL CAPS lines (but not single words like "THE")
    if stripped.isupper() and len(stripped) > 4 and len(stripped.split()) <= 10:
        return True
    for pattern in _HEADING_PATTERNS:
        if pattern.match(stripped):
            return True
    return False


def _extract_sections(text: str) -> List[FSSection]:
    """Split raw text into sections using heuristic heading detection."""
    lines = text.split("\n")
    sections: List[FSSection] = []
    current_heading = "Introduction"
    current_content: List[str] = []
    section_index = 0

    for line in lines:
        if _is_heading(line):
            # Save previous section if it has content
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
            current_heading = line.strip()
            current_content = []
        else:
            current_content.append(line)

    # Don't forget the last section
    content_text = "\n".join(current_content).strip()
    if content_text:
        sections.append(
            FSSection(
                heading=current_heading,
                content=content_text,
                section_index=section_index,
            )
        )

    # If no sections were detected, create one from all content
    if not sections and text.strip():
        sections.append(
            FSSection(
                heading="Document Content",
                content=text.strip(),
                section_index=0,
            )
        )

    return sections


def parse_pdf(filepath: str) -> ParsedFS:
    """Parse a PDF file into structured sections.

    Args:
        filepath: Path to the PDF file on disk.

    Returns:
        ParsedFS with raw text and detected sections.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the PDF is empty or unreadable.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {filepath}")

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        logger.error("Failed to open PDF %s: %s", filepath, exc)
        raise ValueError(f"Cannot read PDF file: {exc}") from exc

    page_texts: List[str] = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
            page_texts.append(text)
        except Exception as exc:
            logger.warning("Failed to extract text from page %d of %s: %s", i, filepath, exc)
            page_texts.append("")

    raw_text = "\n\n".join(page_texts).strip()

    if not raw_text:
        logger.warning("PDF %s produced no text — may be scanned/image-only", filepath)
        return ParsedFS(
            raw_text="",
            sections=[
                FSSection(heading="Document Content", content="[No extractable text — scanned PDF]", section_index=0)
            ],
            metadata={"pages": len(reader.pages), "parser": "pypdf", "warning": "no_text_extracted"},
        )

    sections = _extract_sections(raw_text)

    logger.info(
        "Parsed PDF %s: %d pages, %d sections, %d chars", filepath, len(reader.pages), len(sections), len(raw_text)
    )

    return ParsedFS(
        raw_text=raw_text,
        sections=sections,
        metadata={
            "pages": len(reader.pages),
            "parser": "pypdf",
            "characters": len(raw_text),
        },
    )
