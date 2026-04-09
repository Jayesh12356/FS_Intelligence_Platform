"""Base data structures for document parsing.

All parsers return a ParsedFS instance containing structured sections
extracted from the source document.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FSSection:
    """A single section extracted from an FS document."""

    heading: str
    content: str
    section_index: int

    def to_dict(self) -> dict:
        return {
            "heading": self.heading,
            "content": self.content,
            "section_index": self.section_index,
        }


@dataclass
class ParsedFS:
    """Result of parsing an FS document into structured form."""

    raw_text: str
    sections: List[FSSection] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "raw_text": self.raw_text,
            "sections": [s.to_dict() for s in self.sections],
            "metadata": self.metadata,
        }


@dataclass
class FSChunk:
    """A chunk of text ready for embedding and vector storage."""

    section_heading: str
    text: str
    chunk_index: int
    embedding: Optional[List[float]] = None

    def to_dict(self) -> dict:
        return {
            "section_heading": self.section_heading,
            "text": self.text,
            "chunk_index": self.chunk_index,
        }
