"""
parsers/__init__.py
Factory function that picks the correct parser for a given PDF.

Supports two document types per assignment requirements:
  1. eChallan documents (Lease Deed PDFs with e-Challan on page 1-2)
  2. NA Permission documents (Non-Agricultural Order documents, Gujarat)

Resolution strategy:
  1. Filename keywords (fast — no file I/O)
  2. Content sniffing (loads first 3 pages, tries both parsers)
  3. EChallanParser as fallback (if document type cannot be determined)
"""

import logging
from pathlib import Path

from .echallan_parser import EChallanParser
from .na_permission_parser import NAPermissionParser
from .lease_deed_parser import LeaseDeedParser
from .base_parser import BaseParser

logger = logging.getLogger(__name__)

# ── Filename keyword maps ─────────────────────────────────────────────────────
# These are checked against the lowercase filename stem (no extension).
_NA_FILENAME_KEYWORDS     = ["final order", "iora", "na-permission", "na_permission",
                              "na order", "non-agricultural", "order"]
_CHALLAN_FILENAME_KEYWORDS = ["challan", "echallan", "e-challan"]
_LEASE_DEED_FILENAME_KEYWORDS = ["lease deed", "lease", "lessee", "lessor"]


def get_parser(filepath: str) -> BaseParser:
    """
    Return the best-matching parser for the given PDF file.

    Resolution order:
      1. Filename keywords (fast — no file I/O beyond what's needed).
      2. Content sniffing (loads first 3 pages, tries parsers).
      3. EChallanParser as final fallback.

    Args:
        filepath: Absolute or relative path to a PDF file.

    Returns:
        An instantiated BaseParser subclass.
    """
    name = Path(filepath).stem.lower()
    logger.debug("Resolving parser for: %s (stem=%s)", Path(filepath).name, name)

    # ── Step 1: Filename fast path ─────────────────────────────────────────────
    # Check NA first — "final order" is a strong signal.
    if any(kw in name for kw in _NA_FILENAME_KEYWORDS):
        logger.info("Filename → NA Permission parser  ('%s')", Path(filepath).name)
        return NAPermissionParser(filepath)

    # Check for Lease Deed PDFs (these contain e-Challan on page 1)
    if any(kw in name for kw in _LEASE_DEED_FILENAME_KEYWORDS):
        logger.info("Filename → LeaseDeed/eChallan parser  ('%s')", Path(filepath).name)
        return LeaseDeedParser(filepath)

    # Check explicit e-challan filenames
    if any(kw in name for kw in _CHALLAN_FILENAME_KEYWORDS):
        logger.info("Filename → eChallan parser  ('%s')", Path(filepath).name)
        return EChallanParser(filepath)

    # ── Step 2: Content sniff ──────────────────────────────────────────────────
    logger.info(
        "Filename has no known keywords — sniffing content of '%s'",
        Path(filepath).name,
    )

    # Try each parser in specificity order.
    for ParserClass in (NAPermissionParser, LeaseDeedParser, EChallanParser):
        try:
            parser = ParserClass(filepath)
            doc    = parser.load()
            if doc.doc_type != "unknown":
                logger.info(
                    "Content sniff → %s  (matched by %s)",
                    doc.doc_type, ParserClass.__name__,
                )
                return ParserClass(filepath)
        except Exception as exc:
            logger.warning(
                "Content sniff with %s failed: %s", ParserClass.__name__, exc
            )

    # ── Step 3: Fallback ───────────────────────────────────────────────────────
    logger.warning(
        "Could not determine document type for '%s' — defaulting to EChallanParser",
        Path(filepath).name,
    )
    return EChallanParser(filepath)