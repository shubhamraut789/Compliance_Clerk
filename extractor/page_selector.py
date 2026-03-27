"""
extractor/page_selector.py

Smart page selection for scanned PDFs.

Instead of OCR-ing all 55 pages of a Lease Deed PDF (expensive!),
we pick the ~10-12 pages most likely to contain the fields we need.

Strategy per doc type
─────────────────────
echallan (Lease Deed PDFs):
  • Pages 1–3   : e-Challan receipt (registration fees, stamp duty, dates)
  • Pages 3–5   : Lease Deed cover + parties + survey details
  • Pages 33–35 : Annexure-I (property description / survey table)
  • Page  37    : Schedule of Lease Rent (area, consideration)
  • Page  44    : Village Form 9 (7/12 extract, owner details)
  Plus first page and last 2 pages as catch-all.

na_permission:
  • All pages (NA Permission docs are typically 2–4 pages)

unknown / short docs:
  • All pages (they're small enough to OCR entirely)
"""

from __future__ import annotations
import logging
from typing import List
from parsers.base_parser import PageResult

logger = logging.getLogger(__name__)

# Maximum pages to OCR for a lease deed (to control API cost)
MAX_LEASE_PAGES  = 12
MAX_SHORT_PAGES  = 5   # docs this size or smaller → OCR all pages

# 0-indexed page ranges known to contain key data in Gujarat Lease Deed DNR format
LEASE_DEED_KEY_PAGES_0IDX = [
    0, 1, 2,          # e-Challan pages (registration fees, DNR stamp)
    2, 3, 4,          # Lease Deed cover + survey intro
    32, 33,           # Annexure-I: property/survey description table
    34, 36,           # Schedule of Lease Rent
    43,               # Village Form 9 (7/12 owner details)
    48,               # Sub-Registrar receipt
]


def select_pages(pages: List[PageResult], doc_type: str) -> List[PageResult]:
    """
    Return a deduplicated, ordered subset of pages to send for OCR.

    Args:
        pages:    All PageResult objects from the parsed document.
        doc_type: "echallan" | "na_permission" | "unknown"

    Returns:
        Filtered list of PageResult objects (still in original page order).
    """
    n = len(pages)

    if doc_type == "na_permission" or n <= MAX_SHORT_PAGES:
        # For short docs or NA Permission, use everything
        logger.debug("Page selector: using all %d pages (type=%s)", n, doc_type)
        return pages

    # For lease deed / echallan (long scanned PDFs): pick known key page indices
    indices = set(LEASE_DEED_KEY_PAGES_0IDX)
    indices.add(0)               # always include page 1
    indices.update([n - 2, n - 1])  # last 2 pages

    # Clamp to valid range
    valid_indices = sorted(i for i in indices if 0 <= i < n)

    # Cap at MAX_LEASE_PAGES
    if len(valid_indices) > MAX_LEASE_PAGES:
        valid_indices = valid_indices[:MAX_LEASE_PAGES]

    selected = [pages[i] for i in valid_indices]
    logger.info(
        "Page selector: %d/%d pages selected (indices: %s)",
        len(selected), n, valid_indices,
    )
    return selected