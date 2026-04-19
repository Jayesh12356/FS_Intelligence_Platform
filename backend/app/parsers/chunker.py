"""Section-aware chunker for parsed FS documents.

Splits ParsedFS sections into embedding-ready chunks.
Respects section boundaries — never splits mid-sentence.
Target chunk size: ~800 tokens (~3200 characters).
"""

import logging
import re
from typing import List

from app.parsers.base import FSChunk, FSSection, ParsedFS

logger = logging.getLogger(__name__)

# Approximate max characters per chunk (≈800 tokens)
MAX_CHUNK_CHARS = 3200
# Minimum chunk size to avoid tiny fragments
MIN_CHUNK_CHARS = 100


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentences using regex-based rules."""
    # Split on sentence-ending punctuation followed by whitespace
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def _chunk_section(section: FSSection, base_chunk_index: int) -> List[FSChunk]:
    """Chunk a single section into embedding-ready pieces.

    Short sections become a single chunk.
    Long sections are split at sentence boundaries.
    """
    content = section.content.strip()
    if not content:
        return []

    # If content fits in one chunk, return it directly
    if len(content) <= MAX_CHUNK_CHARS:
        return [
            FSChunk(
                section_heading=section.heading,
                text=content,
                chunk_index=base_chunk_index,
            )
        ]

    # Split into sentences and group into chunks
    sentences = _split_into_sentences(content)
    chunks: List[FSChunk] = []
    current_sentences: List[str] = []
    current_length = 0
    chunk_idx = base_chunk_index

    for sentence in sentences:
        sentence_len = len(sentence)

        # If adding this sentence would exceed the limit, finish current chunk
        if current_length + sentence_len > MAX_CHUNK_CHARS and current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append(
                FSChunk(
                    section_heading=section.heading,
                    text=chunk_text,
                    chunk_index=chunk_idx,
                )
            )
            chunk_idx += 1
            current_sentences = []
            current_length = 0

        current_sentences.append(sentence)
        current_length += sentence_len + 1  # +1 for joining space

    # Don't forget the last chunk
    if current_sentences:
        chunk_text = " ".join(current_sentences)
        # Merge tiny trailing chunks with the previous one
        if len(chunk_text) < MIN_CHUNK_CHARS and chunks:
            chunks[-1] = FSChunk(
                section_heading=chunks[-1].section_heading,
                text=chunks[-1].text + " " + chunk_text,
                chunk_index=chunks[-1].chunk_index,
            )
        else:
            chunks.append(
                FSChunk(
                    section_heading=section.heading,
                    text=chunk_text,
                    chunk_index=chunk_idx,
                )
            )

    return chunks


def chunk_parsed_fs(parsed: ParsedFS) -> List[FSChunk]:
    """Chunk a parsed FS document into embedding-ready pieces.

    Each section is chunked independently. Section boundaries are
    always respected — a chunk never spans multiple sections.

    Args:
        parsed: A ParsedFS result from any parser.

    Returns:
        List of FSChunk instances ready for embedding.
    """
    all_chunks: List[FSChunk] = []
    global_chunk_idx = 0

    for section in parsed.sections:
        section_chunks = _chunk_section(section, global_chunk_idx)
        all_chunks.extend(section_chunks)
        global_chunk_idx += len(section_chunks)

    logger.info(
        "Chunked document: %d sections → %d chunks (avg %d chars/chunk)",
        len(parsed.sections),
        len(all_chunks),
        sum(len(c.text) for c in all_chunks) // max(len(all_chunks), 1),
    )

    return all_chunks


def chunk_text_into_sections(raw_text: str) -> List[dict]:
    """Reconstruct section dicts from raw parsed text.

    Used by the impact router to re-create sections from stored
    parsed_text for diff computation.

    Args:
        raw_text: Raw text of the document (with section headings).

    Returns:
        List of section dicts with heading, content, section_index.
    """
    if not raw_text or not raw_text.strip():
        return []

    # Split on common heading patterns (numbered sections, markdown-style headings)
    heading_pattern = re.compile(
        r"^(?:"
        r"#{1,3}\s+.+"  # Markdown headings
        r"|(?:\d+\.)+\s+.+"  # Numbered headings (1., 1.1., etc.)
        r"|[A-Z][A-Z\s]{2,}$"  # ALL-CAPS headings
        r")",
        re.MULTILINE,
    )

    headings = list(heading_pattern.finditer(raw_text))

    if not headings:
        # No headings found — treat entire text as one section
        return [
            {
                "heading": "Document",
                "content": raw_text.strip(),
                "section_index": 0,
            }
        ]

    sections: List[dict] = []
    for i, match in enumerate(headings):
        heading = match.group().strip().lstrip("#").strip()
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(raw_text)
        content = raw_text[start:end].strip()

        if content:
            sections.append(
                {
                    "heading": heading,
                    "content": content,
                    "section_index": i,
                }
            )

    # If no sections were created but there was text before the first heading
    if headings and headings[0].start() > 0:
        preamble = raw_text[: headings[0].start()].strip()
        if preamble:
            sections.insert(
                0,
                {
                    "heading": "Preamble",
                    "content": preamble,
                    "section_index": 0,
                },
            )
            # Re-index
            for idx, s in enumerate(sections):
                s["section_index"] = idx

    return sections
