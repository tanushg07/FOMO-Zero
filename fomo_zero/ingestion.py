from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from docx import Document

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx"}
MIN_EXTRACTED_TEXT_LENGTH = 20


class IngestionError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class ExtractedNotice:
    text: str
    source_filename: str | None
    content_type: str
    extraction_status: str


def validate_size(content: bytes, max_bytes: int) -> None:
    if len(content) > max_bytes:
        raise IngestionError("file_too_large", f"Input exceeds the {max_bytes}-byte limit")


def extract_notice_text(content: bytes, filename: str) -> ExtractedNotice:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise IngestionError("unsupported_file_type", "Supported file types are TXT, PDF, and DOCX")
    if not content:
        raise IngestionError("invalid_input", "The uploaded file is empty")

    try:
        if extension == ".txt":
            text = content.decode("utf-8-sig").strip()
        elif extension == ".pdf":
            text = _extract_pdf(content)
        else:
            text = _extract_docx(content)
    except IngestionError:
        raise
    except (UnicodeDecodeError, fitz.FileDataError, ValueError, OSError) as exc:
        raise IngestionError("extraction_failed", "The document could not be read") from exc

    if not text:
        status = "ocr_needed" if extension == ".pdf" else "invalid_input"
        message = "The PDF has no selectable text; OCR is required" if extension == ".pdf" else "The document contains no text"
        raise IngestionError(status, message)
    if extension == ".pdf" and len(text) < MIN_EXTRACTED_TEXT_LENGTH:
        raise IngestionError("ocr_needed", "The PDF contains insufficient selectable text; OCR may be required")
    return ExtractedNotice(text, Path(filename).name, extension[1:], "extracted")


def _extract_pdf(content: bytes) -> str:
    with fitz.open(stream=content, filetype="pdf") as document:
        return "\n\n".join(page.get_text("text") for page in document).strip()


def _extract_docx(content: bytes) -> str:
    document = Document(BytesIO(content))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n\n".join(paragraphs).strip()
