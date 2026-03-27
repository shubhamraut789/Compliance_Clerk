"""
parsers/base_parser.py
Abstract base class for all document parsers.

Strategy:
  1. Try native text extraction via pdfplumber.
  2. Normalise text (strip CID garbage) BEFORE counting legible chars.
  3. If legible chars < MIN_CHARS_FOR_TEXT, try pdftotext subprocess
     (handles Identity-H / Shruti font encoding better).
  4. If still too few chars, flag page as scanned → image OCR path.
  5. Return a list of PageResult objects (one per page).

Key fix: CID-encoded PDFs (like Gujarat NA Permission docs) produce
  thousands of (cid:XX) tokens via pdfplumber. Raw char count was
  falsely marking these as text-extractable. Now we count LEGIBLE
  chars after CID stripping to correctly detect scanned/garbled pages.
"""

import logging
import re
import subprocess
import tempfile
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pdfplumber
logger = logging.getLogger(__name__)

# Heuristic: if a page has fewer than this many LEGIBLE chars after
# CID stripping, treat it as needing OCR / rasterisation.
MIN_LEGIBLE_CHARS = 80


# Regex to match pdfplumber CID garbage tokens like (cid:88) or (cid:1044)
_CID_RE = re.compile(r'\(cid:\d+\)')


def normalize_text(text: str) -> str:
    """
    Clean raw pdfplumber output for reliable downstream use.

    Steps:
      1. Strip (cid:XX) tokens produced by Identity-H / CID encoded fonts.
      2. Collapse excess whitespace.
      3. Lowercase for keyword matching.

    This function is SAFE to call multiple times (idempotent).
    """
    if not text:
        return ""
    cleaned = _CID_RE.sub(" ", text)          # remove CID tokens
    cleaned = re.sub(r"[ \t]+", " ", cleaned) # collapse horizontal whitespace
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)  # collapse excessive blank lines
    return cleaned.strip().lower()

def _count_legible_chars(text: str) -> int:
    """Count characters remaining after removing CID garbage tokens."""
    return len(_CID_RE.sub("", text).strip())


@dataclass
class PageResult:
    """Holds the extraction result for a single PDF page."""
    page_number: int
    text: str                               # normalised extractable text
    is_scanned: bool = False                # True → needs LLM-vision OCR
    image_bytes: Optional[bytes] = None    # PNG bytes (for scanned pages)
    extraction_method: str = "pdfplumber"  # "pdfplumber" | "pdftotext" | "ocr"


@dataclass
class DocumentResult:
    """Aggregated result for an entire PDF file."""
    filepath: str
    doc_type: str                # "echallan" | "lease_deed" | "na_permission" | "unknown"
    pages: List[PageResult] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Concatenate all page texts with page separators."""
        parts = []
        for p in self.pages:
            if p.text and p.text.strip():
                parts.append(f"--- PAGE {p.page_number} ---\n{p.text}")
        return "\n\n".join(parts)

    @property
    def has_scanned_pages(self) -> bool:
        return any(p.is_scanned for p in self.pages)


class BaseParser(ABC):
    """
    Abstract document parser.

    Subclasses implement:
      detect_doc_type(text_sample: str) → str
    """

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(f"PDF not found: {filepath}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def load(self) -> DocumentResult:
        """
        Load the PDF, extract  & normalise text from every page.
        Returns a DocumentResult ready for the LLM extractor.
        """
        pages = self._extract_pages()
        first_text = " ".join(p.text for p in pages[:3])
        doc_type = self.detect_doc_type(first_text)

        result = DocumentResult(
            filepath=str(self.filepath),
            doc_type=doc_type,
            pages=pages,
        )
        scanned_count = sum(1 for p in pages if p.is_scanned)
        logger.info(
            "Loaded '%s': %d pages, type=%s, scanned=%s",
            self.filepath.name, len(pages), doc_type,
            scanned_count > 0,
        )
        return result

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _extract_pages(self) -> List[PageResult]:
        """
        Extract text from all pages.

        For each page:
          1. Try pdfplumber.
          2. Count LEGIBLE chars (after CID strip) — not raw chars.
          3. If legible < MIN_LEGIBLE_CHARS → try pdftotext subprocess
             (better at Identity-H / Shruti font encoding).
          4. If still insufficient → mark as scanned, rasterise for OCR.
          5. Store NORMALISED text (CID stripped, whitespace cleaned).
        """
        results: List[PageResult] = []
        try:
            with pdfplumber.open(self.filepath) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    raw_text = page.extract_text() or ""
                    legible_chars = _count_legible_chars(raw_text)
                    method = "pdfplumber"

                    # ── Try pdftotext if pdfplumber gives CID garbage ──────────
                    if legible_chars < MIN_LEGIBLE_CHARS:
                        pdftotext_result = self._extract_page_pdftotext(i)
                        if pdftotext_result and _count_legible_chars(pdftotext_result) > legible_chars:
                            raw_text = pdftotext_result
                            legible_chars = _count_legible_chars(raw_text)
                            method = "pdftotext"
                            logger.debug(
                                "Page %d: pdftotext gave %d legible chars (pdfplumber had %d)",
                                i, legible_chars, _count_legible_chars(page.extract_text() or ""),
                            )

                    # ── Decide: text or scanned ────────────────────────────────
                    is_scanned = legible_chars < MIN_LEGIBLE_CHARS
                    image_bytes: Optional[bytes] = None

                    if is_scanned:
                        logger.debug(
                            "Page %d of '%s': only %d legible chars → flagged for OCR",
                            i, self.filepath.name, legible_chars,
                        )
                        image_bytes = self._rasterise_page(page)
                        method = "ocr"

                    # ── Normalise and store ────────────────────────────────────
                    # Store cleaned text (CID stripped) — the LLM gets clean input
                    normalised = _CID_RE.sub(" ", raw_text)
                    normalised = re.sub(r"[ \t]{2,}", " ", normalised).strip()

                    results.append(PageResult(
                        page_number=i,
                        text=normalised,
                        is_scanned=is_scanned,
                        image_bytes=image_bytes,
                        extraction_method=method,
                    ))
        except Exception as exc:
            logger.error("PDF extraction failed for '%s': %s", self.filepath.name, exc)
            raise

        return results
    
    def _extract_page_pdftotext(self, page_number: int) -> str:
        """
        Use the pdftotext CLI to extract a single page.
        Returns empty string if pdftotext is unavailable or fails.
        pdftotext handles Identity-H CID fonts far better than pdfplumber.
        """
        try:
            result = subprocess.run(
                [
                    "pdftotext",
                    "-f", str(page_number),
                    "-l", str(page_number),
                    "-layout",          # preserve spatial layout
                    str(self.filepath),
                    "-",                # output to stdout
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.debug("pdftotext not available or timed out for page %d", page_number)
        return ""
    
    def _rasterise_page(self, page) -> Optional[bytes]:
        """
        Rasterise a pdfplumber Page to PNG bytes for LLM-vision OCR.
        Returns None if rasterisation fails.
        """
        try:
            from config import OCR_PAGE_DPI
            
            import io
            img = page.to_image(resolution=OCR_PAGE_DPI)
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
        Inspect a normalised sample of the document text and return
        the doc type string: "echallan", "lease_deed", "na_permission",
        or "unknown".

        text_sample is already normalised (CID-stripped, lowercased)
        because it comes from PageResult.text which is normalised at
        extraction time.
        """
        ...