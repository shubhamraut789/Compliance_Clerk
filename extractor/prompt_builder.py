"""
extractor/prompt_builder.py
Builds structured extraction prompts for the LLM, one per document type.

The prompts instruct the LLM to return **only** valid JSON matching the
schema keys defined in config.py. This is the first layer of Schema
Enforcement — the second layer is schema_enforcer.py which validates
the LLM response.
"""

import json
from config import ECHALLAN_SCHEMA, NA_PERMISSION_SCHEMA

SYSTEM_PROMPT = (
    "You are an expert document extraction assistant. "
    "You accurately extract structured fields from government and legal "
    "documents, including documents in Gujarati. "
    "You always respond with valid JSON only — no markdown, no explanation."
)

# ── Per-doc-type extraction instructions ───────────────────────────────────────

_ECHALLAN_INSTRUCTIONS = """
You are reading an e-Challan document issued by the Inspector General of
Registration, Revenue Department, Government of Gujarat.

This is a Cyber Treasury e-Challan — a registration fee receipt for a
lease deed / property registration. It is NOT a traffic violation challan.

Extract these fields from the document:
{schema}

Specific instructions:
- "challan_number": Use the Transaction No (ટ્રોઝેકશન નંબર) from the payment table.
- "vehicle_number": This field does not apply. Set to "N/A".
- "violation_date": Use the Date (તારીખ) from the payment table row (DD-MM-YYYY format).
- "amount": Use the Total Amount (કુલ રકમ) in Rs. Numeric only, no currency symbol.
- "offence_description": Use the Account Head description (e.g. "Registration Fee").
- "payment_status": Set to "Paid" if a Transaction No is present, otherwise "Unpaid".
- "survey_number": Look in Property Details section for the survey/block number.
- "lease_deed_doc_no": The Lease Deed document number (e.g. "1141/2026") — often
  visible in the handwritten stamp area or in the title.
- "lease_area": Lease area in sq.m. from Property Details if visible. Numeric only.
- "lease_start_date": The date the e-Challan was issued / printed (DD/MM/YYYY).
- "village": Village name from Property Details (e.g. "Rampura Mota").
- "echallan_number": The e-Challan reference number (e.g. "INGJ260120156942").
  This is different from the Transaction No — look for a separate reference code.
- "valid_up_to": Validity/expiry date of the e-Challan (DD/MM/YYYY).
- "tenure_years": Lease tenure in years if stated anywhere (e.g. "99 Yrs" or "25 Yrs").

Return ONLY a valid JSON object with exactly these keys. No markdown fences,
no explanation, no extra text.
"""

_NA_PERMISSION_INSTRUCTIONS = """
You are reading a Non-Agricultural (NA) Permission order issued by a
Gujarat government authority (Prant Adhikari / Mamlatdar).

The document is primarily in Gujarati. It contains an iORA order number
and grants permission for non-agricultural use of land.

Extract these fields from the document:
{schema}

Specific instructions:
- "survey_number": The survey/block number (સર્વે/બ્લોક નંબર), e.g. "251/P2" or "257".
- "land_area": Total land area in sq.m. as stated in the order. Numeric only.
- "owner_name": Full name of the applicant / land owner (અરજદાર).
- "order_date": Date of the order (તા.) in DD/MM/YYYY format.
- "authority_name": Name and designation of the issuing authority
  (e.g. "Prant Adhikari, Dhanera").
- "order_number": The full iORA order reference (e.g. "iORA/31/02/112/25/2026").
- "taluka": Taluka name where the land is situated.
- "district": District name where the land is situated.
- "lease_term": Duration in the format "X years Y months Z days".

Return ONLY a valid JSON object with exactly these keys. No markdown fences,
no explanation, no extra text.
"""


def build_extraction_prompt(doc_type: str, text: str, schema: dict = None) -> str:
    """
    Build a structured extraction prompt for the given document type.

    Args:
        doc_type:  "echallan" or "na_permission"
        text:      Extracted / OCR'd text from the document.
        schema:    Optional override for the schema dict.

    Returns:
        A prompt string ready to send to the LLM.
    """
    if doc_type == "echallan":
        template = _ECHALLAN_INSTRUCTIONS
        schema = schema or ECHALLAN_SCHEMA
    elif doc_type == "na_permission":
        template = _NA_PERMISSION_INSTRUCTIONS
        schema = schema or NA_PERMISSION_SCHEMA
    else:
        # Generic fallback
        template = (
            "Extract the following fields from this document:\n{schema}\n\n"
            "Return ONLY a valid JSON object with exactly these keys."
        )
        schema = schema or {}

    schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
    instructions = template.format(schema=schema_str)

    prompt = (
        f"{instructions}\n\n"
        f"--- DOCUMENT TEXT ---\n"
        f"{text}\n"
        f"--- END OF DOCUMENT ---"
    )

    return prompt