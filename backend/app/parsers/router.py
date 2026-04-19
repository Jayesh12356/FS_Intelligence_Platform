"""Parser router — dispatches to the correct parser based on file type.

Handles the full parsing lifecycle:
  1. Determines parser from file extension
  2. Updates document status to PARSING
  3. Invokes the parser
  4. Updates document with parsed_text and status PARSED (or PARSE_FAILED)
"""

import logging
import uuid
from pathlib import Path

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FSDocument, FSDocumentStatus
from app.parsers.base import ParsedFS
from app.parsers.docx_parser import parse_docx
from app.parsers.pdf_parser import parse_pdf
from app.parsers.txt_parser import parse_txt

logger = logging.getLogger(__name__)

# Map file extensions to parser functions
_PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".txt": parse_txt,
}


def get_parser(filetype: str):
    """Get the parser function for a given file extension.

    Args:
        filetype: File extension (e.g. ".pdf", ".docx", ".txt")

    Returns:
        Parser function or None if unsupported.
    """
    return _PARSERS.get(filetype.lower())


async def parse_document(
    fs_id: str,
    db: AsyncSession,
) -> ParsedFS:
    """Parse an uploaded document and update the database.

    This is the main entry point for the parsing pipeline.
    It loads the document from DB, determines the parser,
    runs parsing, and persists the result.

    Args:
        fs_id: UUID string of the FSDocument to parse.
        db: Async database session.

    Returns:
        ParsedFS result with extracted sections.

    Raises:
        ValueError: If document not found or unsupported file type.
        RuntimeError: If parsing fails.
    """
    # Convert string ID to UUID object for SQLAlchemy compatibility
    try:
        doc_uuid = uuid.UUID(fs_id) if isinstance(fs_id, str) else fs_id
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid document ID: {fs_id}")

    # Load the document
    result = await db.execute(select(FSDocument).where(FSDocument.id == doc_uuid))
    doc = result.scalar_one_or_none()

    if doc is None:
        raise ValueError(f"Document {fs_id} not found")

    if not doc.file_path:
        raise ValueError(f"Document {fs_id} has no file path — upload may have failed")

    filepath = doc.file_path
    ext = Path(filepath).suffix.lower()
    parser_fn = get_parser(ext)

    if parser_fn is None:
        doc.status = FSDocumentStatus.ERROR
        await db.flush()
        raise ValueError(f"No parser available for file type: {ext}")

    # Update status to PARSING
    doc.status = FSDocumentStatus.PARSING
    await db.flush()

    logger.info("Parsing document %s (%s) with %s parser", fs_id, doc.filename, ext)

    try:
        parsed = await anyio.to_thread.run_sync(parser_fn, filepath)
    except Exception as exc:
        logger.error("Parsing failed for document %s: %s", fs_id, exc)
        doc.status = FSDocumentStatus.ERROR
        await db.flush()
        raise RuntimeError(f"Parsing failed: {exc}") from exc

    # Persist parsed text and update status
    doc.parsed_text = parsed.raw_text
    doc.original_text = parsed.raw_text  # Also store as original_text for reference
    doc.status = FSDocumentStatus.PARSED
    await db.flush()

    logger.info(
        "Document %s parsed: %d sections, %d chars",
        fs_id,
        len(parsed.sections),
        len(parsed.raw_text),
    )

    return parsed
