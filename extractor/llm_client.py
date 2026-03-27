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
import re
import time
from typing import Optional

from google import genai
from audit.logger import AuditLogger
from config import LLM_MODEL, MAX_TOKENS
from extractor.prompt_builder import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Rate-limit retry settings
MAX_RATE_RETRIES = 3       # how many times to retry on 429
INITIAL_BACKOFF  = 10      # seconds before first retry
MAX_BACKOFF      = 60      # max wait between retries

class LLMClient:
    """
    Wraps the Google GenAI SDK for single-turn extraction calls.
    Handles 429 rate-limit errors with automatic exponential backoff.

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
        Automatically retries on 429 rate-limit errors with backoff.

        Args:
            prompt:      The user-turn content.
            doc_type:    Used for audit logging ("echallan" | "na_permission").
            file_name:   Source filename, for audit logging.
            image_bytes: Optional PNG image bytes (for OCR / scanned pages).

        Returns:
            Raw string response from the LLM.

        Raises:
            RuntimeError if the API call fails after all retries
        """
        contents = self._build_contents(prompt, image_bytes)
        start_ms = int(time.time() * 1000)
        raw_response: Optional[str] = None
        error_msg: Optional[str] = None
        parsed_ok = False

        try:
            raw_response = self._call_with_backoff(contents)
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
    
    def _call_with_backoff(self, contents: list) -> str:
        """
        Call Gemini API with exponential backoff on 429 rate-limit errors.

        Parses the retryDelay from the error response if available,
        otherwise uses exponential backoff starting at INITIAL_BACKOFF.
        """
        last_exc = None
        backoff = INITIAL_BACKOFF

        for attempt in range(1, MAX_RATE_RETRIES + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config={
                        "system_instruction": SYSTEM_PROMPT,
                        "max_output_tokens": MAX_TOKENS,
                    },
                )

                # Extract text — response.text can be None for thinking models
                text = response.text
                if text is None:
                    # Fallback: try to get text from candidates
                    try:
                        parts = response.candidates[0].content.parts
                        text = "".join(
                            p.text for p in parts if hasattr(p, "text") and p.text
                        )
                    except (IndexError, AttributeError):
                        text = ""

                    if text:
                        logger.debug("Extracted text from response.candidates (%d chars)", len(text))
                    else:
                        logger.warning("LLM returned empty response (no text in candidates either)")

                return text or ""

            except Exception as exc:
                last_exc = exc
                exc_str = str(exc)

                # Check if this is a 429 rate-limit error
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    # Try to parse the retry delay from the response
                    wait_time = self._parse_retry_delay(exc_str) or backoff

                    if attempt < MAX_RATE_RETRIES:
                        logger.warning(
                            "Rate limited (429) — waiting %.0fs before retry %d/%d",
                            wait_time, attempt, MAX_RATE_RETRIES,
                        )
                        time.sleep(wait_time)
                        backoff = min(backoff * 2, MAX_BACKOFF)  # exponential
                        continue

                # Not a 429, or retries exhausted — re-raise
                raise

        # Should not reach here, but just in case
        raise last_exc

    @staticmethod
    def _parse_retry_delay(error_text: str) -> Optional[float]:
        """
        Extract the retryDelay value from a Gemini 429 error response.
        Example: "retryDelay': '37s'" → 37.0
        """
        match = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)", error_text)
        if match:
            return float(match.group(1))
        return None
    
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