"""
extractor/doc_extractor.py
Orchestrator that ties together:
  parsing → page selection → OCR → LLM extraction → schema enforcement.

Pipeline for each PDF:
  1. get_parser() → load & detect document type.
  2. page_selector → pick the ~10-12 key pages (for large scanned PDFs).
  3. For scanned eChallan: send first page images DIRECTLY to extraction
     LLM (vision-based extraction is more accurate than OCR → text → extract).
  4. For text-based docs: build prompt with extracted text.
  5. SchemaEnforcer → call LLM + validate JSON + retry on failure.
  6. Return a dict with extracted fields + metadata.
"""

import io
import logging
from pathlib import Path
from typing import Optional, Dict, List

from PIL import Image
from config import (
    ECHALLAN_SCHEMA,
    NA_PERMISSION_SCHEMA,
)
from parsers import get_parser
from extractor.llm_client import LLMClient
from extractor.prompt_builder import build_extraction_prompt
from extractor.schema_enforcer import SchemaEnforcer, _get_schema
from extractor.page_selector import select_pages
from extractor.ocr_engine import OCREngine

logger = logging.getLogger(__name__)


class DocumentExtractor:
    """
    Processes a single PDF: parse → select pages → OCR/vision → extract → validate.

    For eChallan (scanned Lease Deed PDFs):
      - Sends first 2-3 page images DIRECTLY to the LLM for vision extraction.
      - Also OCRs key pages (Annexure, Schedule, etc.) for supplementary text.

    For NA Permission (text-based):
      - Sends extracted text to the LLM for field extraction.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.llm = LLMClient(api_key=api_key)
        self.enforcer = SchemaEnforcer(self.llm)
        self.ocr = OCREngine(self.llm)

    def process(self, pdf_path: str) -> Dict:
        """
        Process a single PDF and return extracted fields.

        Returns:
            dict with:
              - All schema fields (values or None)
              - "source_file": filename
              - "doc_type": detected document type
              - "_error": error message if extraction failed (None on success)
        """
        filepath = Path(pdf_path)
        logger.info("Processing: %s", filepath.name)

        # ── Step 1: Parse the PDF ──────────────────────────────────────────────
        parser = get_parser(str(filepath))
        doc = parser.load()
        doc_type = doc.doc_type
        schema = _get_schema(doc_type)

        logger.info(
            "Detected type: %s (%d pages, scanned=%s)",
            doc_type, len(doc.pages), doc.has_scanned_pages,
        )

        result = {
            "source_file": filepath.name,
            "doc_type": doc_type,
            "_error": None,
        }

        # ── Step 2: Select key pages ───────────────────────────────────────────
        selected_pages = select_pages(doc.pages, doc_type)

        # ── Step 3: Extract based on document type ─────────────────────────────
        if doc.has_scanned_pages and doc_type == "echallan":
            # For scanned eChallan / Lease Deed PDFs:
            # Use DIRECT VISION extraction on first pages (e-Challan receipt)
            # + OCR supplementary pages for lease deed details
            validated = self._extract_scanned_echallan(
                selected_pages, schema, filepath.name,
            )
        elif doc.has_scanned_pages:
            # Other scanned docs: OCR then extract
            validated = self._extract_via_ocr(
                selected_pages, doc_type, schema, filepath.name,
            )
        else:
            # Text-based docs (NA Permission): direct text extraction
            text = doc.full_text
            if not text.strip():
                result["_error"] = "No extractable text found"
                logger.error("No content to extract from %s", filepath.name)
                return result

            prompt = build_extraction_prompt(doc_type, text, schema)
            validated = self.enforcer.extract(
                prompt=prompt,
                doc_type=doc_type,
                file_name=filepath.name,
            )

        # Merge validated fields into result
        result.update(validated)

        if validated.get("_error"):
            logger.error("Extraction failed for %s: %s", filepath.name, validated["_error"])
        else:
            logger.info("Extraction successful for %s", filepath.name)

        return result

    # ── Scanned eChallan: vision-based extraction ─────────────────────────────

    def _extract_scanned_echallan(
        self,
        pages: List,
        schema: dict,
        file_name: str,
    ) -> Dict:
        """
        For large scanned Lease Deed PDFs:
        1. Send first 3 page images directly to LLM for vision extraction
           (e-Challan receipt + Lease Deed cover page).
        2. OCR key pages (Annexure, Schedule) for supplementary text.
        3. Combine everything into one extraction prompt with images + text.
        """
        # Collect images from first 3 pages (e-Challan + Lease Deed cover)
        echallan_pages = [p for p in pages if p.page_number <= 3 and p.image_bytes]
        other_pages = [p for p in pages if p.page_number > 3]

        # OCR the remaining key pages for supplementary context
        supplementary_text = ""
        if other_pages:
            ocr_results = self.ocr.ocr_pages(other_pages, file_name=file_name)
            text_parts = []
            for page in other_pages:
                page_text = ocr_results.get(page.page_number, "")
                if page_text and page_text.strip():
                    text_parts.append(f"--- PAGE {page.page_number} ---\n{page_text}")
            supplementary_text = "\n\n".join(text_parts)

        # Build the extraction contents: images + prompt
        contents: list = []

        # Add e-Challan page images
        for page in echallan_pages:
            pil_img = Image.open(io.BytesIO(page.image_bytes))
            contents.append(f"[e-Challan Page {page.page_number}]")
            contents.append(pil_img)

        logger.info(
            "Vision extraction: %d page images + %d chars supplementary text",
            len(echallan_pages),
            len(supplementary_text),
        )

        # Build the extraction prompt
        import json
        schema_str = json.dumps(schema, indent=2, ensure_ascii=False)

        prompt = (
            "You are reading scanned pages from a Lease Deed registration document "
            "from Gujarat, India. The document is partly in Gujarati (ગુજરાતી) and "
            "partly in English.\n\n"
            "The first pages shown are the e-Challan (Cyber Treasury registration fee "
            "receipt) and Lease Deed cover page.\n\n"
        )

        if supplementary_text:
            prompt += (
                "Below is OCR'd text from additional key pages of the same document "
                "(Annexure, Schedule, etc.):\n\n"
                f"{supplementary_text}\n\n"
            )

        prompt += (
            f"Extract these fields from the images AND the supplementary text:\n"
            f"{schema_str}\n\n"
            "Specific instructions for eChallan fields:\n"
            "- \"challan_number\": Transaction No (ટ્રોઝેકશન નંબર) from the payment table.\n"
            "- \"vehicle_number\": Set to \"N/A\" (not a traffic challan).\n"
            "- \"violation_date\": Date (તારીખ) from the payment row (DD-MM-YYYY).\n"
            "- \"amount\": Total Amount (કુલ રકમ) in Rs. Numeric only.\n"
            "- \"offence_description\": Account Head description (e.g. \"Registration Fee\").\n"
            "- \"payment_status\": \"Paid\" if Transaction No is present.\n"
            "- \"survey_number\": Survey/block number from property details (e.g. \"251/P2\").\n"
            "- \"lease_deed_doc_no\": Lease Deed document number (e.g. \"141/2026\").\n"
            "- \"lease_area\": Area in sq.m. Numeric only.\n"
            "- \"lease_start_date\": Date the deed was registered (DD/MM/YYYY).\n"
            "- \"village\": Village name (e.g. \"Rampura Mota\" / \"રામપુરા મોટા\").\n"
            "- \"echallan_number\": e-Challan reference (e.g. \"INGJ260120156942\").\n"
            "- \"valid_up_to\": Validity/expiry date of the e-Challan (DD/MM/YYYY).\n"
            "- \"tenure_years\": Lease tenure (e.g. \"99 Yrs\").\n\n"
            "Return ONLY a valid JSON object with exactly these keys. "
            "No markdown fences, no explanation."
        )
        contents.append(prompt)

        # Use SchemaEnforcer with image contents
        # We need to call the LLM directly with multi-image contents
        return self._enforced_vision_call(
            contents, "echallan", schema, file_name,
        )

    def _enforced_vision_call(
        self,
        contents: list,
        doc_type: str,
        schema: dict,
        file_name: str,
    ) -> Dict:
        """
        Call LLM with multi-image contents, parse JSON, retry on failure.
        Similar to SchemaEnforcer.extract() but works with raw contents.
        """
        from extractor.schema_enforcer import _parse_json, _fill_missing_keys, _null_dict
        from extractor.prompt_builder import SYSTEM_PROMPT
        from config import MAX_RETRIES, MAX_TOKENS
        import time

        last_raw = ""

        for attempt in range(1 + MAX_RETRIES):
            try:
                if attempt == 0:
                    call_contents = contents
                else:
                    # Correction: just send text prompt (no images)
                    logger.warning(
                        "Vision extraction retry %d/%d for '%s'",
                        attempt, MAX_RETRIES, file_name,
                    )
                    keys_list = ", ".join(f'"{k}"' for k in schema)
                    call_contents = [
                        f"Your previous response was not valid JSON. "
                        f"You returned:\n{last_raw[:500]}\n\n"
                        f"Please respond with ONLY a valid JSON object containing "
                        f"exactly these keys: {keys_list}\n"
                        f"No markdown, no explanation — just the JSON."
                    ]

                response = self.llm._client.models.generate_content(
                    model=self.llm.model,
                    contents=call_contents,
                    config={
                        "system_instruction": SYSTEM_PROMPT,
                        "max_output_tokens": MAX_TOKENS,
                    },
                )

                raw = response.text
                if not raw:
                    try:
                        parts = response.candidates[0].content.parts
                        raw = "".join(
                            p.text for p in parts
                            if hasattr(p, "text") and p.text
                        )
                    except (IndexError, AttributeError):
                        raw = ""

                last_raw = raw or ""

                # Log to audit
                self.llm.audit.log(
                    doc_type=doc_type,
                    file_name=file_name,
                    prompt=f"Vision extraction attempt {attempt + 1}",
                    raw_response=raw[:500] if raw else "(empty)",
                    parsed_ok=bool(raw),
                    model=self.llm.model,
                )

                if not raw:
                    logger.warning("Attempt %d: empty response", attempt + 1)
                    continue

                parsed = _parse_json(raw)
                if parsed is not None:
                    return _fill_missing_keys(parsed, schema)

                logger.warning(
                    "Attempt %d: could not parse JSON (first 200): %s",
                    attempt + 1, raw[:200],
                )

            except Exception as exc:
                logger.error("Vision call failed attempt %d: %s", attempt + 1, exc)
                # Check for rate limit and wait
                exc_str = str(exc)
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    import re
                    match = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+)", exc_str)
                    wait = int(match.group(1)) if match else 30
                    logger.warning("Rate limited — waiting %ds", wait)
                    time.sleep(wait)
                elif attempt == MAX_RETRIES:
                    return _null_dict(schema, error=str(exc))

        return _null_dict(
            schema, error=f"Vision extraction failed after {1 + MAX_RETRIES} attempts"
        )

    # ── Generic OCR-based extraction ──────────────────────────────────────────

    def _extract_via_ocr(
        self,
        pages: list,
        doc_type: str,
        schema: dict,
        file_name: str,
    ) -> Dict:
        """
        OCR scanned pages → build text prompt → SchemaEnforcer extraction.
        Used for non-eChallan scanned documents.
        """
        ocr_results = self.ocr.ocr_pages(pages, file_name=file_name)

        text_parts = []
        for page in pages:
            page_text = ocr_results.get(page.page_number, page.text)
            if page_text and page_text.strip():
                text_parts.append(f"--- PAGE {page.page_number} ---\n{page_text}")
        text = "\n\n".join(text_parts)

        if not text.strip():
            from extractor.schema_enforcer import _null_dict
            return _null_dict(schema, error="No OCR text extracted")

        prompt = build_extraction_prompt(doc_type, text, schema)

        # Also grab first scanned image for vision
        image_bytes = None
        for page in pages:
            if page.is_scanned and page.image_bytes:
                image_bytes = page.image_bytes
                break

        return self.enforcer.extract(
            prompt=prompt,
            doc_type=doc_type,
            file_name=file_name,
            image_bytes=image_bytes,
        )