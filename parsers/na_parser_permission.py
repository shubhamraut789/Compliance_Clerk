"""
parsers/na_permission_parser.py
Parser for NA (Non-Agricultural) Permission / Order documents issued by
Government of Gujarat authorities (Mamlatdar, Talati, etc.)
"""

import logging
from .base_parser import BaseParser
from config import NA_PERMISSION_KEYWORDS

logger = logging.getLogger(__name__)

# Gujarati keywords for NA permission documents
_GUJARATI_NA = "\u0a85\u0a95\u0aaa\u0aa7\u0ab2 \u0ab8\u0a82\u0aae\u0aa4\u0ac0"  # "non-agricultural"
_GUJARATI_ORDER = "\u0a85\u0aaa\u0ac7\u0a95\u0acd\u0ab8\u0abe"  # "order"


class NAPermissionParser(BaseParser):
    """
    Parses Gujarat NA (Non-Agricultural) Permission PDFs.
    These are documents authorizing non-agricultural use of land.
    
    Key fields to find:
      - Survey Number
      - Land Area
      - Owner Name
      - Order Date
      - Authority Name (Mamlatdar, etc.)
      - Order Number / Reference
      - Taluka and District
    """

    def detect_doc_type(self, text_sample: str) -> str:
        """Return 'na_permission' if keywords are found, else 'unknown'."""
        hits = sum(1 for kw in NA_PERMISSION_KEYWORDS if kw in text_sample)
        if hits >= 2 or "non-agricultural" in text_sample or _GUJARATI_NA in text_sample:
            logger.debug("NAPermissionParser detected doc type: na_permission (hits=%d)", hits)
            return "na_permission"
        return "unknown"