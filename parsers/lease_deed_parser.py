"""
parsers/lease_deed_parser.py
Parser for Lease Deed documents which contain e-Challan (registration fee
receipts) on page 1-2, followed by the actual lease deed content.

These are issued by the Inspector General of Registration, Revenue Department,
Government of Gujarat.

The e-Challan fields (Challan Number, Amount, Date, Payment Status) are
extracted from page 1-2, and lease deed fields (Lease Area, Lease Start Date,
Lease Deed Doc No) from subsequent pages.

For the purpose of this assignment, these documents are classified as
"echallan" type since the primary extraction target is the e-Challan page.
"""

import logging
from .base_parser import BaseParser, normalize_text
from config import ECHALLAN_KEYWORDS, LEASE_DEED_KEYWORDS

logger = logging.getLogger(__name__)


class LeaseDeedParser(BaseParser):
    """
    Parses Lease Deed PDFs that contain e-Challan on page 1.

    These PDFs are large (50+ pages) — the first page is the Cyber Treasury
    e-Challan receipt for registration fees, followed by the actual lease deed.

    Classified as "echallan" for the assignment's 2-type system.
    """

    def detect_doc_type(self, text_sample: str) -> str:
        """Return 'echallan' if lease deed / e-challan keywords are found.

        Falls back to 'echallan' even if text is empty/unreadable,
        because this parser is only selected when the filename already
        matched lease deed keywords.
        """
        text_sample = normalize_text(text_sample)

        # If text is empty (scanned pages), default to echallan since
        # the filename already told us this is a lease deed PDF.
        if not text_sample.strip():
            logger.debug("LeaseDeedParser: no readable text (scanned) → defaulting to echallan")
            return "echallan"

        # Strong signals: "e-challan" header or "lease deed" in text
        if "e-challan" in text_sample or "echallan" in text_sample:
            logger.debug("LeaseDeedParser detected e-Challan header → echallan")
            return "echallan"

        # Check lease deed keywords
        lease_hits = sum(1 for kw in LEASE_DEED_KEYWORDS if kw in text_sample)
        if lease_hits >= 2:
            logger.debug("LeaseDeedParser detected lease deed keywords (hits=%d) → echallan", lease_hits)
            return "echallan"

        # Check echallan keywords
        challan_hits = sum(1 for kw in ECHALLAN_KEYWORDS if kw in text_sample)
        if challan_hits >= 2:
            logger.debug("LeaseDeedParser detected eChallan keywords (hits=%d) → echallan", challan_hits)
            return "echallan"

        # Fallback: since this parser was filename-matched, default to echallan
        return "echallan"