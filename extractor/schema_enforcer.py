"""
extractor/schema_enforcer.py
Ensures the LLM always returns a valid JSON dict with expected keys.

Strategy:
  1. Try json.loads() on the raw response.
  2. If that fails, strip markdown fences and extract via brace-counting.
  3. If still failing, send a correction prompt to the LLM (up to MAX_RETRIES).
  4. If all retries fail, return a nulled-out dict with an _error key.

This is the second layer of Schema Enforcement:
  Layer 1: prompt_builder.py instructs the LLM to return valid JSON.
  Layer 2: This module VALIDATES and guarantees a conforming dict.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from config import MAX_RETRIES, ECHALLAN_SCHEMA, NA_PERMISSION_SCHEMA

logger = logging.getLogger(__name__)


class SchemaValidationError(Exception):
    """Raised when LLM output does not conform to the expected schema."""
    pass


# ── Pure validation functions (usable standalone) ──────────────────────────────

def _extract_json_block(raw: str) -> str:
    """
    Extract a JSON object from raw LLM output that may contain
    markdown fences, preamble text, or trailing explanation.

    Strategy:
      1. Strip ```json ... ``` fences.
      2. Find the first { ... } block using brace counting.
         (More robust than greedy regex for nested JSON.)
    """
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    # Try to find the outermost JSON object using brace counting
    start = cleaned.find("{")
    if start == -1:
        raise SchemaValidationError("No JSON object found in LLM response")

    depth = 0
    for i in range(start, len(cleaned)):
        if cleaned[i] == "{":
            depth += 1
        elif cleaned[i] == "}":
            depth -= 1
            if depth == 0:
                return cleaned[start:i + 1]

    # Unbalanced braces
    raise SchemaValidationError("Unbalanced braces in LLM response")


def _parse_json(raw: str) -> Optional[Dict]:
    """
    Try to parse raw string as JSON.
    Handles markdown fences and preamble/trailing text.
    Returns None if completely unparseable.
    """
    if not raw:
        return None

    # 1. Direct parse (fastest path)
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 2. Extract via brace-counting (handles fences + noise)
    try:
        json_str = _extract_json_block(raw)
        result = json.loads(json_str)
        if isinstance(result, dict):
            return result
    except (SchemaValidationError, json.JSONDecodeError):
        pass

    logger.debug("Could not parse JSON from: %s", raw[:200])
    return None


def _fill_missing_keys(data: Dict, schema: Dict) -> Dict:
    """Ensure all schema keys exist in the output; fill with None if absent."""
    missing = []
    for key in schema:
        if key not in data:
            data[key] = None
            missing.append(key)
    if missing:
        logger.warning("Schema enforcement: filled missing keys with null: %s", missing)
    return data


def _null_dict(schema: Dict, error: str = "") -> Dict:
    """Return a dict of all-null values with an _error field."""
    result = {k: None for k in schema}
    result["_error"] = error
    return result


def _get_schema(doc_type: str) -> Dict:
    """Return the schema dict for a given document type."""
    if doc_type == "echallan":
        return ECHALLAN_SCHEMA
    elif doc_type == "na_permission":
        return NA_PERMISSION_SCHEMA
    else:
        return ECHALLAN_SCHEMA  # fallback


# ── Standalone function (backward-compatible) ─────────────────────────────────

def enforce_schema(raw_llm_text: str, schema: Dict[str, str]) -> Dict[str, Optional[str]]:
    """
    Parse and validate LLM output against the expected schema.

    Raises:
        SchemaValidationError: If the response cannot be parsed as JSON.
    """
    if not raw_llm_text or not raw_llm_text.strip():
        raise SchemaValidationError("Empty LLM response")

    parsed = _parse_json(raw_llm_text)
    if parsed is None:
        raise SchemaValidationError("Could not parse JSON from LLM response")

    return _fill_missing_keys(parsed, schema)


# ── Class-based enforcer with built-in LLM retries ────────────────────────────

class SchemaEnforcer:
    """
    Wraps LLMClient calls and guarantees a dict output.
    Handles retries with correction prompts internally.

    Usage:
        enforcer = SchemaEnforcer(llm_client)
        data = enforcer.extract(
            prompt=build_extraction_prompt(...),
            doc_type="echallan",
            file_name="deed.pdf",
        )
    """

    def __init__(self, llm_client):
        self.client = llm_client

    def extract(
        self,
        prompt: str,
        doc_type: str,
        file_name: str,
        image_bytes: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """
        Call the LLM, parse JSON, retry on failure.

        Returns a dict guaranteed to have all expected keys.
        On total failure, returns nulled dict with '_error' key set.
        """
        schema = _get_schema(doc_type)
        raw: Optional[str] = None

        for attempt in range(1 + MAX_RETRIES):
            try:
                if attempt == 0:
                    raw = self.client.call(
                        prompt=prompt,
                        doc_type=doc_type,
                        file_name=file_name,
                        image_bytes=image_bytes,
                    )
                else:
                    # Correction attempt — tell LLM what went wrong
                    logger.warning(
                        "Schema enforcement retry %d/%d for '%s'",
                        attempt, MAX_RETRIES, file_name,
                    )
                    correction = self._build_correction_prompt(raw or "", doc_type)
                    raw = self.client.call(
                        prompt=correction,
                        doc_type=doc_type,
                        file_name=file_name,
                    )

                parsed = _parse_json(raw)
                if parsed is not None:
                    return _fill_missing_keys(parsed, schema)

            except Exception as exc:
                logger.error("LLM call failed on attempt %d: %s", attempt + 1, exc)
                if attempt == MAX_RETRIES:
                    return _null_dict(schema, error=str(exc))

        # All retries exhausted
        logger.error("All retries failed for '%s'", file_name)
        return _null_dict(schema, error=f"Could not parse JSON after {1 + MAX_RETRIES} attempts")

    @staticmethod
    def _build_correction_prompt(bad_response: str, doc_type: str) -> str:
        """Build a correction prompt when the LLM response was invalid JSON."""
        schema = _get_schema(doc_type)
        keys_list = ", ".join(f'"{k}"' for k in schema)
        return (
            f"Your previous response was not valid JSON. "
            f"Here is what you returned:\n\n"
            f"{bad_response[:500]}\n\n"
            f"Please respond with ONLY a valid JSON object containing "
            f"exactly these keys: {keys_list}\n\n"
            f"No markdown fences, no explanation — just the JSON object."
        )