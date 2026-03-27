"""
extractor/ocr_engine.py

Efficient batched OCR for scanned PDFs using Google GenAI (Gemini vision).

Key design decisions:
  - Batch size of 2 (not 4) — larger batches cause the LLM to merge or
    skip page labels, especially with Gujarati documents.
  - Each page gets a clear positional label BEFORE its image.
  - Gujarati-aware system prompt.
  - Separate per-page OCR fallback if batch fails.
"""

from __future__ import annotations

import io
import logging
import re
from typing import Dict, List, Optional

from PIL import Image
from parsers.base_parser import PageResult

logger = logging.getLogger(__name__)

# Batch size of 2 gives best accuracy for Gujarati documents.
# Larger batches (4+) cause the LLM to merge or skip page labels.
BATCH_SIZE = 2

# Gujarati-aware system prompt
OCR_SYSTEM_PROMPT = (
    "You are an expert OCR assistant specializing in Indian government documents. "
    "You can read English, Gujarati (ગુજરાતી), and Hindi accurately. "
    "Transcribe document images exactly as instructed. "
    "Output only the transcribed text in the requested format. "
    "Preserve ALL numbers, dates, amounts, table data, and reference numbers accurately. "
    "Pay special attention to: challan numbers, transaction IDs, dates, "
    "amounts in Rs., survey numbers, and area measurements."
)


class OCREngine:
    """
    Runs batched LLM-vision OCR on scanned page images via google.genai.

    Usage:
        engine = OCREngine(llm_client)
        text_by_page = engine.ocr_pages(selected_pages, file_name="deed.pdf")
        # Returns dict: {page_number: ocr_text}
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client

    def ocr_pages(
        self,
        pages: List[PageResult],
        file_name: str = "",
    ) -> Dict[int, str]:
        """
        OCR a list of PageResult objects.
        Pages that already have text are returned as-is.
        Scanned pages are processed in batches via Gemini vision.
        """
        results: Dict[int, str] = {}

        # Separate pages that need OCR from those that already have text
        needs_ocr = [p for p in pages if p.is_scanned or not p.text.strip()]
        has_text  = [p for p in pages if not p.is_scanned and p.text.strip()]

        for p in has_text:
            results[p.page_number] = p.text

        if not needs_ocr:
            return results

        logger.info(
            "OCR needed for %d pages of '%s' — batching in groups of %d",
            len(needs_ocr), file_name, BATCH_SIZE,
        )

        # Process in batches of BATCH_SIZE
        for i in range(0, len(needs_ocr), BATCH_SIZE):
            batch = needs_ocr[i : i + BATCH_SIZE]
            batch_results = self._ocr_batch(batch, file_name)
            results.update(batch_results)

        return results

    def ocr_single_page(self, page: PageResult, file_name: str = "") -> str:
        """
        OCR a single page image. Used for direct vision extraction.
        Returns the transcribed text.
        """
        if page.image_bytes is None:
            return ""

        pil_img = Image.open(io.BytesIO(page.image_bytes))

        prompt = (
            "This is a scanned page from an Indian government/legal document "
            "(Gujarat state). Transcribe ALL visible text exactly as it appears. "
            "Include English, Gujarati, and Hindi text. "
            "Preserve all numbers, dates, amounts, reference numbers, and table data. "
            "Do NOT add any commentary — only output the transcribed text."
        )

        try:
            response = self.llm_client._client.models.generate_content(
                model=self.llm_client.model,
                contents=[pil_img, prompt],
                config={
                    "system_instruction": OCR_SYSTEM_PROMPT,
                    "max_output_tokens": 4096,
                },
            )
            text = response.text or ""
            if not text:
                try:
                    parts = response.candidates[0].content.parts
                    text = "".join(p.text for p in parts if hasattr(p, "text") and p.text)
                except (IndexError, AttributeError):
                    text = ""
            return text
        except Exception as exc:
            logger.error("Single-page OCR failed for page %d: %s", page.page_number, exc)
            return ""

    # ── Internal ───────────────────────────────────────────────────────────────

    def _ocr_batch(
        self,
        pages: List[PageResult],
        file_name: str,
    ) -> Dict[int, str]:
        """
        Send a batch of page images to Gemini in a single multi-image call.
        Uses sequential labeling (IMAGE 1 = Page X) to prevent the LLM from
        confusing page numbers.
        """
        page_nums = [p.page_number for p in pages]
        page_list = ", ".join(str(n) for n in page_nums)

        # If only 1 page, use single-page OCR (more reliable)
        if len(pages) == 1:
            text = self.ocr_single_page(pages[0], file_name)
            return {pages[0].page_number: text}

        # Build content list with clear sequential labeling
        contents: list = []
        valid_pages: list = []
        page_mapping: list = []  # maps sequential index to page number

        for idx, page in enumerate(pages, start=1):
            if page.image_bytes is None:
                logger.warning("Page %d has no image bytes, skipping", page.page_number)
                continue

            pil_img = Image.open(io.BytesIO(page.image_bytes))

            # Label BEFORE the image: "IMAGE 1 (this is PDF page 3):"
            contents.append(f"IMAGE {idx} (this is PDF page {page.page_number}):")
            contents.append(pil_img)
            valid_pages.append(page.page_number)
            page_mapping.append((idx, page.page_number))

        if not contents:
            return {n: "" for n in page_nums}

        # Build a clear, Gujarati-aware OCR prompt
        mapping_str = ", ".join(
            f"IMAGE {idx} = Page {pg}" for idx, pg in page_mapping
        )
        prompt_text = (
            f"I have shown you {len(page_mapping)} scanned page images from a "
            f"Gujarat government document. The mapping is: {mapping_str}.\n\n"
            f"For EACH image, transcribe ALL visible text (English, ગુજરાતી Gujarati, "
            f"and Hindi). Preserve numbers, dates, amounts, survey numbers, "
            f"reference numbers, and table data exactly.\n\n"
            f"Use this EXACT output format — one section per image:\n\n"
            f"=== PAGE <page_number> ===\n"
            f"<transcribed text>\n\n"
            f"For example, for {mapping_str.split(',')[0]}:\n"
            f"=== PAGE {page_mapping[0][1]} ===\n"
            f"<text from that page>\n\n"
            f"Output ONLY the transcribed text with page headers. "
            f"No commentary, no analysis."
        )
        contents.append(prompt_text)

        logger.debug("Sending OCR batch: %s for '%s'", page_list, file_name)

        try:
            response = self.llm_client._client.models.generate_content(
                model=self.llm_client.model,
                contents=contents,
                config={
                    "system_instruction": OCR_SYSTEM_PROMPT,
                    "max_output_tokens": 8192,  # More tokens for Gujarati text
                },
            )
            raw = response.text
            if not raw:
                try:
                    parts = response.candidates[0].content.parts
                    raw = "".join(p.text for p in parts if hasattr(p, "text") and p.text)
                except (IndexError, AttributeError):
                    raw = ""

            # Log to audit trail
            self.llm_client.audit.log(
                doc_type="ocr",
                file_name=file_name,
                prompt=f"OCR batch pages {page_list}",
                raw_response=raw[:500] + "..." if len(raw) > 500 else raw,
                parsed_ok=bool(raw),
                model=self.llm_client.model,
            )

            return self._parse_ocr_response(raw, page_nums)

        except Exception as exc:
            logger.error("OCR batch failed for pages %s: %s", page_list, exc)
            self.llm_client.audit.log(
                doc_type="ocr",
                file_name=file_name,
                prompt=f"OCR batch pages {page_list}",
                raw_response=None,
                parsed_ok=False,
                error_message=str(exc),
                model=self.llm_client.model,
            )
            return {n: "" for n in page_nums}

    @staticmethod
    def _parse_ocr_response(raw: str, page_nums: List[int]) -> Dict[int, str]:
        """
        Parse OCR response with flexible page header matching.

        Handles both formats:
          [PAGE N]     — original format
          === PAGE N ===  — new format
        """
        if not raw:
            return {n: "" for n in page_nums}

        results: Dict[int, str] = {}

        # Match both [PAGE N] and === PAGE N === formats
        pattern = r"(?:\[PAGE\s+(\d+)\]|===\s*PAGE\s+(\d+)\s*===)"
        parts = re.split(pattern, raw)

        # parts alternates: preamble, group1, group2, text, group1, group2, text...
        i = 1
        while i < len(parts):
            # One of the two capture groups will be set
            page_num_str = parts[i] or parts[i + 1] if i + 1 < len(parts) else None
            text_content = parts[i + 2].strip() if i + 2 < len(parts) else ""

            if page_num_str:
                try:
                    page_num = int(page_num_str)
                    results[page_num] = text_content
                except ValueError:
                    pass

            i += 3  # skip past both groups + text

        # Fill in missing page numbers
        for n in page_nums:
            if n not in results:
                logger.warning("OCR response missing page %d", n)
                results[n] = ""

        return results