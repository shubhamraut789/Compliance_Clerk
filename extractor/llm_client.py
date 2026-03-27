"""
extractor/llm_client.py
Thin wrapper around the Google GenAI SDK (google-genai).

Responsibilities:
  - Send prompt + optional image to the LLM.
  - Log every call (prompt + raw response) to the AuditLogger.
  - Return the raw string response for downstream parsing.

Uses the new google-genai SDK (not the deprecated google-generativeai).
Migration: https://ai.google.dev/gemini-api/docs/migrate
"""

import logging
import os
import time
from typing import Optional

from google import genai
from audit.logger import AuditLogger
from config import LLM_MODEL, MAX_TOKENS
from extractor.prompt_builder import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Wraps the Google GenAI SDK for single-turn extraction calls.

    Usage:
        client = LLMClient()
        raw = client.call(
            prompt="Extract fields from...",
            doc_type="echallan",
            file_name="deed.pdf",
        )
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or LLM_MODEL
        self.audit = AuditLogger()

        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY must be set (or passed to LLMClient).")

        # New SDK: create a centralized Client object
        self._client = genai.Client(api_key=self.api_key)

        logger.info("LLMClient ready (model=%s)", self.model)

    def call(
        self,
        prompt: str,
        doc_type: str = "unknown",
        file_name: str = "",
        image_bytes: Optional[bytes] = None,
    ) -> str:
        """
        Send a prompt (optionally with an image) to the LLM.

        Args:
            prompt:      The user-turn content.
            doc_type:    Used for audit logging ("echallan" | "na_permission").
            file_name:   Source filename, for audit logging.
            image_bytes: Optional PNG image bytes (for OCR / scanned pages).

        Returns:
            Raw string response from the LLM.

        Raises:
            RuntimeError if the API call fails.
        """
        contents = self._build_contents(prompt, image_bytes)
        start_ms = int(time.time() * 1000)
        raw_response: Optional[str] = None
        error_msg: Optional[str] = None
        parsed_ok = False

        try:
            # New SDK: client.models.generate_content(...)
            response = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "max_output_tokens": MAX_TOKENS,
                },
            )
            raw_response = response.text
            parsed_ok = True
            logger.debug("LLM responded (%d chars)", len(raw_response or ""))

        except Exception as exc:
            error_msg = str(exc)
            logger.error("LLM API error: %s", exc)
            raise RuntimeError("LLM API call failed") from exc

        finally:
            duration_ms = int(time.time() * 1000) - start_ms
            self.audit.log(
                doc_type=doc_type,
                file_name=file_name,
                prompt=prompt,
                raw_response=raw_response,
                parsed_ok=parsed_ok,
                error_message=error_msg,
                model=self.model,
                duration_ms=duration_ms,
            )

        return raw_response or ""

    @staticmethod
    def _build_contents(prompt: str, image_bytes: Optional[bytes] = None) -> list:
        """
        Build contents list for the GenAI SDK.

        For text-only: returns [prompt_text]
        For image+text: returns [PIL.Image, prompt_text]

        The google-genai SDK auto-converts PIL.Image objects.
        """
        if image_bytes is not None:
            import io
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            return [img, prompt]

        return [prompt]