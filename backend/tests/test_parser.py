"""Tests for L2 document parsing pipeline.

Tests:
- TXT parsing (section detection, chunking)
- PDF parsing (mock-based)
- DOCX parsing (mock-based)
- Parse API endpoint
- Chunker logic
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Unit Tests: TXT Parser ─────────────────────────────


class TestTxtParser:
    """Test plain-text parser."""

    def test_parse_txt_with_sections(self, tmp_path):
        """TXT with clear section headings should produce multiple sections."""
        from app.parsers.txt_parser import parse_txt

        content = """1. INTRODUCTION
This is the introduction to the functional specification.
It describes the overall purpose of the system.

2. REQUIREMENTS
The system shall support user authentication.
The system shall provide dashboard functionality.
The system shall integrate with external APIs.

3. NON-FUNCTIONAL REQUIREMENTS
Performance: Response time under 200ms.
Security: All data encrypted at rest.
"""
        txt_file = tmp_path / "test_spec.txt"
        txt_file.write_text(content, encoding="utf-8")

        result = parse_txt(str(txt_file))

        assert result.raw_text.strip() != ""
        assert len(result.sections) >= 3
        assert result.metadata["parser"] == "txt"

        # Check that section headings were detected
        headings = [s.heading for s in result.sections]
        assert any("INTRODUCTION" in h for h in headings)
        assert any("REQUIREMENTS" in h for h in headings)

    def test_parse_txt_empty(self, tmp_path):
        """Empty TXT file should produce empty ParsedFS."""
        from app.parsers.txt_parser import parse_txt

        txt_file = tmp_path / "empty.txt"
        txt_file.write_text("", encoding="utf-8")

        result = parse_txt(str(txt_file))

        assert result.raw_text == ""
        assert len(result.sections) == 0

    def test_parse_txt_no_headings(self, tmp_path):
        """TXT without headings should produce a single section."""
        from app.parsers.txt_parser import parse_txt

        content = "This is a simple document with no section headings.\nJust some plain text."
        txt_file = tmp_path / "plain.txt"
        txt_file.write_text(content, encoding="utf-8")

        result = parse_txt(str(txt_file))

        assert len(result.sections) >= 1
        assert result.sections[0].content.strip() != ""

    def test_parse_txt_file_not_found(self):
        """Non-existent file should raise FileNotFoundError."""
        from app.parsers.txt_parser import parse_txt

        with pytest.raises(FileNotFoundError):
            parse_txt("/nonexistent/file.txt")


# ── Unit Tests: PDF Parser ─────────────────────────────


class TestPdfParser:
    """Test PDF parser."""

    def test_parse_pdf_file_not_found(self):
        """Non-existent PDF should raise FileNotFoundError."""
        from app.parsers.pdf_parser import parse_pdf

        with pytest.raises(FileNotFoundError):
            parse_pdf("/nonexistent/file.pdf")

    def test_heading_detection(self):
        """Test heading heuristic helpers."""
        from app.parsers.pdf_parser import _is_heading

        assert _is_heading("1. INTRODUCTION") is True
        assert _is_heading("REQUIREMENTS OVERVIEW") is True
        assert _is_heading("1.1 Sub-section details") is True
        assert _is_heading("Section 3") is True
        assert _is_heading("This is a normal sentence.") is False
        assert _is_heading("") is False


# ── Unit Tests: DOCX Parser ────────────────────────────


class TestDocxParser:
    """Test DOCX parser."""

    def test_parse_docx_file_not_found(self):
        """Non-existent DOCX should raise FileNotFoundError."""
        from app.parsers.docx_parser import parse_docx

        with pytest.raises(FileNotFoundError):
            parse_docx("/nonexistent/file.docx")


# ── Unit Tests: Chunker ────────────────────────────────


class TestChunker:
    """Test the section-aware chunker."""

    def test_chunk_short_section(self):
        """Short sections should produce a single chunk."""
        from app.parsers.base import FSSection, ParsedFS
        from app.parsers.chunker import chunk_parsed_fs

        parsed = ParsedFS(
            raw_text="Hello world",
            sections=[FSSection(heading="Intro", content="Hello world", section_index=0)],
        )

        chunks = chunk_parsed_fs(parsed)

        assert len(chunks) == 1
        assert chunks[0].section_heading == "Intro"
        assert chunks[0].text == "Hello world"
        assert chunks[0].chunk_index == 0

    def test_chunk_long_section(self):
        """Long sections should be split into multiple chunks."""
        from app.parsers.base import FSSection, ParsedFS
        from app.parsers.chunker import chunk_parsed_fs

        # Create a long section (~5000 chars, should split into 2+ chunks)
        long_content = ". ".join(
            [f"This is sentence number {i} with some extra text to make it longer" for i in range(100)]
        )

        parsed = ParsedFS(
            raw_text=long_content,
            sections=[FSSection(heading="Long Section", content=long_content, section_index=0)],
        )

        chunks = chunk_parsed_fs(parsed)

        assert len(chunks) >= 2
        # All chunks should belong to the same section
        for chunk in chunks:
            assert chunk.section_heading == "Long Section"

    def test_chunk_multiple_sections(self):
        """Multiple sections should produce ordered chunks."""
        from app.parsers.base import FSSection, ParsedFS
        from app.parsers.chunker import chunk_parsed_fs

        parsed = ParsedFS(
            raw_text="Section 1 content.\nSection 2 content.",
            sections=[
                FSSection(heading="Section 1", content="Content for section one.", section_index=0),
                FSSection(heading="Section 2", content="Content for section two.", section_index=1),
            ],
        )

        chunks = chunk_parsed_fs(parsed)

        assert len(chunks) == 2
        assert chunks[0].section_heading == "Section 1"
        assert chunks[1].section_heading == "Section 2"
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1

    def test_chunk_empty_parsed(self):
        """Empty ParsedFS should produce no chunks."""
        from app.parsers.base import ParsedFS
        from app.parsers.chunker import chunk_parsed_fs

        parsed = ParsedFS(raw_text="", sections=[])
        chunks = chunk_parsed_fs(parsed)

        assert len(chunks) == 0


# ── Unit Tests: Parser Router ──────────────────────────


class TestParserRouter:
    """Test parser routing logic."""

    def test_get_parser_pdf(self):
        """PDF extension should route to pdf parser."""
        from app.parsers.router import get_parser

        assert get_parser(".pdf") is not None

    def test_get_parser_docx(self):
        """DOCX extension should route to docx parser."""
        from app.parsers.router import get_parser

        assert get_parser(".docx") is not None

    def test_get_parser_txt(self):
        """TXT extension should route to txt parser."""
        from app.parsers.router import get_parser

        assert get_parser(".txt") is not None

    def test_get_parser_unsupported(self):
        """Unsupported extension should return None."""
        from app.parsers.router import get_parser

        assert get_parser(".xlsx") is None
        assert get_parser(".ppt") is None


# ── Integration Tests: Parse API ───────────────────────


class TestParseAPI:
    """Test the parse endpoint via HTTP client."""

    @pytest.mark.asyncio
    async def test_parse_uploaded_txt(self, client):
        """Upload a TXT file, parse it, verify sections in response."""
        # Upload a test file
        content = b"""1. INTRODUCTION
This is a test functional specification document.
It covers the user authentication module.

2. REQUIREMENTS
REQ-001: The system shall support SSO login.
REQ-002: The system shall enforce password complexity rules.
REQ-003: The system shall lock accounts after 5 failed attempts.

3. ACCEPTANCE CRITERIA
All requirements must be verified through automated tests.
"""
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("test_fs.txt", content, "text/plain")},
        )
        assert response.status_code == 200
        upload_data = response.json()["data"]
        doc_id = upload_data["id"]

        # Parse the document
        parse_response = await client.post(f"/api/fs/{doc_id}/parse")
        assert parse_response.status_code == 200

        parse_data = parse_response.json()["data"]
        assert parse_data["status"] == "PARSED"
        assert parse_data["sections_count"] >= 2
        assert len(parse_data["sections"]) >= 2

        # Verify sections have content
        for section in parse_data["sections"]:
            assert "heading" in section
            assert "content" in section
            assert section["content"].strip() != ""

    @pytest.mark.asyncio
    async def test_parse_nonexistent_document(self, client):
        """Parsing a non-existent document should return 400."""
        response = await client.post("/api/fs/00000000-0000-0000-0000-000000000000/parse")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_document_status_after_parse(self, client):
        """After parsing, document status should be PARSED."""
        content = b"Simple test content for parsing."
        response = await client.post(
            "/api/fs/upload",
            files={"file": ("simple.txt", content, "text/plain")},
        )
        doc_id = response.json()["data"]["id"]

        # Parse
        await client.post(f"/api/fs/{doc_id}/parse")

        # Check status
        status_response = await client.get(f"/api/fs/{doc_id}/status")
        assert status_response.status_code == 200
        assert status_response.json()["data"]["status"] == "PARSED"
