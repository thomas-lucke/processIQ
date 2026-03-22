"""Universal document parser using Docling.

Supports: PDF, DOCX, PPTX, Excel, HTML, images
Extracts text and semantic chunks (tables, headings, lists) for LLM processing.

Flow: File → Docling → ParsedDocument → normalizer.py (LLM) → ProcessData
"""

import logging
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO

from docling.datamodel.base_models import ConversionStatus
from docling.document_converter import DocumentConverter
from docling_core.types.io import DocumentStream

from processiq.exceptions import ExtractionError

logger = logging.getLogger(__name__)

# Supported file extensions
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    ".xlsx",
    ".xls",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".bmp",
}


@dataclass
class DocumentChunk:
    """A semantic chunk from a parsed document.

    Chunks preserve document structure (tables, headings, lists) for better
    LLM understanding compared to plain text splitting.
    """

    content: str
    chunk_type: str  # "text", "table", "heading", "list", "picture_caption"
    page: int | None = None
    confidence: float = 1.0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """Result of parsing a document with Docling.

    Attributes:
        text: Full text content (for LLM extraction).
        markdown: Markdown-formatted content (preserves structure).
        chunks: Semantic chunks for granular processing.
        metadata: Source file info (name, format, page count).
        success: Whether parsing succeeded.
        error: Error message if parsing failed.
    """

    text: str
    markdown: str
    chunks: list[DocumentChunk]
    metadata: dict[str, object] = field(default_factory=dict)
    success: bool = True
    error: str | None = None

    @property
    def has_tables(self) -> bool:
        """Check if document contains tables."""
        return any(c.chunk_type == "table" for c in self.chunks)

    @property
    def page_count(self) -> int:
        """Get number of pages in document."""
        count = self.metadata.get("page_count", 0)
        return int(count) if isinstance(count, int | float) else 0


# Singleton converter instance (expensive to create)
_converter: DocumentConverter | None = None


def _get_converter() -> DocumentConverter:
    """Get or create the DocumentConverter instance."""
    global _converter
    if _converter is None:
        logger.debug("Initializing DocumentConverter")
        _converter = DocumentConverter()
    return _converter


def _extract_chunks(doc: Any) -> list[DocumentChunk]:
    """Extract semantic chunks from a DoclingDocument."""
    chunks = []

    # Extract text items with their types
    for item, level in doc.iterate_items():
        item_type = type(item).__name__

        # Map Docling item types to our chunk types
        if "Table" in item_type:
            # Tables - export as markdown for structure
            if hasattr(item, "export_to_markdown"):
                content = item.export_to_markdown()
            else:
                content = str(item)
            chunk_type = "table"
        elif "Heading" in item_type or "Title" in item_type:
            content = item.text if hasattr(item, "text") else str(item)
            chunk_type = "heading"
        elif "List" in item_type:
            content = item.text if hasattr(item, "text") else str(item)
            chunk_type = "list"
        elif "Picture" in item_type:
            # Pictures - capture caption if available
            content = item.caption if hasattr(item, "caption") else ""
            if not content:
                continue  # Skip pictures without captions
            chunk_type = "picture_caption"
        else:
            # Default text content
            content = item.text if hasattr(item, "text") else str(item)
            chunk_type = "text"

        if content and content.strip():
            # Get page number if available
            page = None
            if hasattr(item, "prov") and item.prov:
                prov = item.prov[0] if isinstance(item.prov, list) else item.prov
                if hasattr(prov, "page_no"):
                    page = prov.page_no

            chunks.append(
                DocumentChunk(
                    content=content.strip(),
                    chunk_type=chunk_type,
                    page=page,
                    metadata={"level": level, "item_type": item_type},
                )
            )

    return chunks


def parse_document(file_bytes: bytes, filename: str) -> ParsedDocument:
    """Parse any supported document format.

    This is the main entry point for document parsing. Supports PDF, DOCX,
    PPTX, Excel, HTML, and images.

    Args:
        file_bytes: Raw file content.
        filename: Original filename (used for format detection).

    Returns:
        ParsedDocument with extracted text, markdown, and semantic chunks.

    Raises:
        ExtractionError: If the file format is unsupported or parsing fails.

    Example:
        >>> with open("process.pdf", "rb") as f:
        ...     doc = parse_document(f.read(), "process.pdf")
        >>> print(doc.text[:100])
        >>> for chunk in doc.chunks:
        ...     if chunk.chunk_type == "table":
        ...         print(chunk.content)
    """
    logger.info("Parsing document: %s (%d bytes)", filename, len(file_bytes))

    # Validate file extension
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ExtractionError(
            message=f"Unsupported file format: {suffix}",
            source="docling_parser",
            user_message=f"File format '{suffix}' is not supported. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    try:
        converter = _get_converter()

        # Create DocumentStream from bytes
        stream = DocumentStream(name=filename, stream=BytesIO(file_bytes))

        # Convert document
        logger.debug("Converting document with Docling")
        result = converter.convert(stream)

        # Check conversion status
        if result.status != ConversionStatus.SUCCESS:
            error_msgs = [str(e) for e in result.errors] if result.errors else []
            error_str = "; ".join(error_msgs) if error_msgs else "Unknown error"
            logger.error("Document conversion failed: %s", error_str)
            return ParsedDocument(
                text="",
                markdown="",
                chunks=[],
                metadata={"filename": filename, "format": suffix},
                success=False,
                error=f"Conversion failed: {error_str}",
            )

        # Extract content
        doc = result.document
        text = doc.export_to_text()
        markdown = doc.export_to_markdown()
        chunks = _extract_chunks(doc)

        # Build metadata
        metadata = {
            "filename": filename,
            "format": suffix,
            "page_count": len(result.pages) if result.pages else 0,
            "has_tables": any(c.chunk_type == "table" for c in chunks),
            "chunk_count": len(chunks),
        }

        logger.info(
            "Parsed document: %d pages, %d chunks, %d chars",
            metadata["page_count"],
            len(chunks),
            len(text),
        )

        return ParsedDocument(
            text=text,
            markdown=markdown,
            chunks=chunks,
            metadata=metadata,
            success=True,
        )

    except ExtractionError:
        raise
    except Exception as e:
        logger.exception("Document parsing failed: %s", e)
        raise ExtractionError(
            message=f"Document parsing failed: {e}",
            source="docling_parser",
            user_message=f"Failed to parse '{filename}'. The file may be corrupted or password-protected.",
        ) from e


def parse_file(file_path: Path | str) -> ParsedDocument:
    """Parse a document from a file path.

    Convenience wrapper around parse_document() for file system access.

    Args:
        file_path: Path to the document file.

    Returns:
        ParsedDocument with extracted content.

    Example:
        >>> doc = parse_file("data/process_description.pdf")
        >>> print(f"Extracted {len(doc.text)} characters")
    """
    path = Path(file_path)
    if not path.exists():
        raise ExtractionError(
            message=f"File not found: {path}",
            source="docling_parser",
            user_message=f"File '{path.name}' not found.",
        )

    with open(path, "rb") as f:
        return parse_document(f.read(), path.name)


def parse_from_stream(stream: BinaryIO, filename: str) -> ParsedDocument:
    """Parse a document from a file-like object.

    Useful for multipart file uploads which provide file-like objects.

    Args:
        stream: File-like object with read() method.
        filename: Original filename for format detection.

    Returns:
        ParsedDocument with extracted content.

    Example:
        >>> uploaded_file = st.file_uploader("Upload document")
        >>> if uploaded_file:
        ...     doc = parse_from_stream(uploaded_file, uploaded_file.name)
    """
    file_bytes = stream.read()
    if isinstance(file_bytes, bytearray | memoryview):
        file_bytes = bytes(file_bytes)
    return parse_document(file_bytes, filename)
