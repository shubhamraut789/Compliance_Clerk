"""
parsers/base_parser.py
Abstract base class for all document parsers.

Strategy:
  1. Try native text extraction via pdfplumber (fast, no LLM cost).
  2. If a page has < MIN_CHARS characters, treat it as scanned/image-based
     and flag it for LLM-OCR fallback.
  3. Return a list of PageResult objects (one per page).
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pdfplumber

logger = logging.getLogger(__name__)

# Heuristic: if a page yields fewer than this many chars, consider it scanned
MIN_CHARS_FOR_TEXT = 80


@dataclass
class PageResult:
    """Holds the extraction result for a single PDF page."""
    page_number: int
    text: str                    # extracted or OCR text
    is_scanned: bool = False     # True → text came from LLM-OCR
    image_bytes: Optional[bytes] = None   # raw PNG bytes (only for scanned pages)


@dataclass
class DocumentResult:
    """Aggregated result for an entire PDF file."""
    filepath: str
    doc_type: str                # "echallan" | "lease_deed" | "unknown"
    pages: List[PageResult] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Concatenate all page texts with page separators."""
        parts = []
        for p in self.pages:
            parts.append(f"--- PAGE {p.page_number} ---\n{p.text}")
        return "\n\n".join(parts)

    @property
    def has_scanned_pages(self) -> bool:
        return any(p.is_scanned for p in self.pages)


class BaseParser(ABC):
    """
    Abstract document parser.

    Subclasses implement:
      - detect_doc_type(text) → str
      - get_relevant_pages(pages) → List[PageResult]  (optional override)
    """

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(f"PDF not found: {filepath}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def load(self) -> DocumentResult:
        """
        Load the PDF, extract text from every page.
        Returns a DocumentResult ready for the LLM extractor.
        """
        pages = self._extract_pages()
        first_text = " ".join(p.text for p in pages[:3]).lower()
        doc_type = self.detect_doc_type(first_text)

        result = DocumentResult(
            filepath=str(self.filepath),
            doc_type=doc_type,
            pages=pages,
        )
        logger.info(
            "Loaded '%s': %d pages, type=%s, scanned=%s",
            self.filepath.name, len(pages), doc_type, result.has_scanned_pages
        )
        return result

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _extract_pages(self) -> List[PageResult]:
        """
        Use pdfplumber for native text extraction.
        Pages that yield too little text are flagged as scanned.
        """
        results: List[PageResult] = []
        try:
            with pdfplumber.open(self.filepath) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    text = text.strip()

                    is_scanned = len(text) < MIN_CHARS_FOR_TEXT
                    image_bytes: Optional[bytes] = None

                    if is_scanned:
                        logger.debug(
                            "Page %d of '%s' has only %d chars — flagged as scanned",
                            i, self.filepath.name, len(text)
                        )
                        image_bytes = self._rasterise_page(page)

                    results.append(PageResult(
                        page_number=i,
                        text=text,
                        is_scanned=is_scanned,
                        image_bytes=image_bytes,
                    ))
        except Exception as exc:
            logger.error("pdfplumber failed on '%s': %s", self.filepath.name, exc)
            raise

        return results

    def _rasterise_page(self, page) -> Optional[bytes]:
        """
        Rasterise a single pdfplumber Page object to PNG bytes.
        Used as input for LLM-vision OCR.
        Returns None if rasterisation fails.
        """
        try:
            from config import OCR_PAGE_DPI
            img = page.to_image(resolution=OCR_PAGE_DPI)
            import io
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as exc:
            logger.warning("Could not rasterise page: %s", exc)
            return None

    # ── Abstract methods ───────────────────────────────────────────────────────

    @abstractmethod
    def detect_doc_type(self, text_sample: str) -> str:
        """
        Inspect a sample of the document text and return the doc type string.
        E.g. "echallan", "lease_deed", "unknown".
        """
        ...