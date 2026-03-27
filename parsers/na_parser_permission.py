"""
parsers/na_permission_parser.py
Parser for NA (Non-Agricultural) Permission / Order documents issued by
Government of Gujarat authorities (Mamlatdar, Prant Adhikari, etc.)

Fixes applied:
  - "iora/" used as single definitive signal (unique to NA orders)
  - Keyword list tightened to avoid false positives against Lease Deeds
  - Hit threshold raised to 3 (was 2) since generic words like "survey"
    also appear in Lease Deed documents
"""

import logging
from .base_parser import BaseParser, normalize_text
from config import NA_PERMISSION_KEYWORDS

logger = logging.getLogger(__name__)

# Gujarati keywords for NA permission documents
_GUJARATI_NA    = "\u0a85\u0a95\u0aaa\u0aa7\u0ab2 \u0ab8\u0a82\u0aae\u0aa4\u0ac0"  # non-agricultural
_GUJARATI_ORDER = "\u0a85\u0aaa\u0ac7\u0a95\u0acd\u0ab8\u0abe"                      # order

# iORA/ is the unique prefix on every Gujarat NA permission order number
# e.g. iORA/31/02/112/25/2026  — appears in no other document type
_IORA_SIGNAL = "iora/"


class NAPermissionParser(BaseParser):
    """
    Parses Gujarat NA (Non-Agricultural) Permission PDFs.
    These are orders authorising non-agricultural use of land, issued
    by the Prant Adhikari / Mamlatdar under the Gujarat tenancy laws.
    
    Key fields to find:
      - Survey Number
      - Land Area
      - Owner Name / Applicant
      - Order Date
      - Authority Name (Prant Adhikari, Mamlatdar, etc.)
      - Taluka and District
    """

    def detect_doc_type(self, text_sample: str) -> str:
        """Return 'na_permission' if strong signals are found, else 'unknown'."""
        text_sample = normalize_text(text_sample)

        # DEFINITIVE SIGNAL: iORA/ prefix is unique to NA permission orders
        # This single match is sufficient — no other document type uses it.
        if _IORA_SIGNAL in text_sample:
            logger.debug("NAPermissionParser: definitive iORA/ signal found → na_permission")
            return "na_permission"

        # SECONDARY SIGNALS: require 3 hits to avoid false positives against
        # Lease Deed documents which also mention survey/taluka/district.
        hits = sum(1 for kw in NA_PERMISSION_KEYWORDS if kw in text_sample)
        if hits >= 3 or "non-agricultural" in text_sample or _GUJARATI_NA in text_sample:
            logger.debug("NAPermissionParser detected doc type: na_permission (hits=%d)", hits)
            return "na_permission"
        return "unknown"