"""
parsers/lease_deed_parser.py
Parser for Lease Deed / NA Permission documents registered under Gujarat
Sub-Registrar offices (DNR format).
"""

import logging
from .base_parser import BaseParser
from config import LEASE_DEED_KEYWORDS

logger = logging.getLogger(__name__)

# Gujarati word for "lease" - using unicode escapes for portability
_GUJARATI_LEASE = "\u0ab2\u0ac0\u0a9d"   # \u0ab2\u0ac0\u0a9d = \u0c32\u0c40\u0c1d


class LeaseDeedParser(BaseParser):
    """
    Parses Gujarat Lease Deed PDFs (DNR registration format).
    """

    def detect_doc_type(self, text_sample: str) -> str:
        """Return 'lease_deed' if keywords are found, else 'unknown'."""
        hits = sum(1 for kw in LEASE_DEED_KEYWORDS if kw in text_sample)
        if hits >= 2 or "lease deed" in text_sample or _GUJARATI_LEASE in text_sample:
            logger.debug("LeaseDeedParser detected doc type: lease_deed (hits=%d)", hits)
            return "lease_deed"
        return "unknown"
