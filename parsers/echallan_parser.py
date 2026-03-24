"""
parsers/echallan_parser.py
Parser for eChallan documents issued by the Inspector General of Registration,
Revenue Department, Government of Gujarat.
"""

import logging
from .base_parser import BaseParser
from config import ECHALLAN_KEYWORDS

logger = logging.getLogger(__name__)


class EChallanParser(BaseParser):
    """
    Parses Gujarat eChallan PDFs.

    Key fields to find:
      - Application No / Transaction No
      - Vehicle Number
      - Date / violation date
      - Amount (Rs.)
      - Offence description
      - Payment status
    """

    def detect_doc_type(self, text_sample: str) -> str:
        """Return 'echallan' if keywords are found, else 'unknown'."""
        hits = sum(1 for kw in ECHALLAN_KEYWORDS if kw in text_sample)
        if hits >= 2 or "e-challan" in text_sample or "echallan" in text_sample:
            logger.debug("EChallanParser detected doc type: echallan (hits=%d)", hits)
            return "echallan"
        return "unknown"