"""
config.py
Central configuration for the Compliance Clerk pipeline.

Document types supported:
  1. eChallan — Cyber Treasury registration fee receipts (page 1 of Lease Deed PDFs)
  2. NA Permission — iORA non-agricultural permission orders (Gujarat)
"""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "output"
LOGS_DIR   = BASE_DIR / "logs"
DB_PATH    = LOGS_DIR / "audit.db"

# Ensure runtime directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── LLM settings ──────────────────────────────────────────────────────────────
LLM_MODEL      = os.getenv("LLM_MODEL", "gemini-3-flash-preview")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
MAX_TOKENS     = 4096
MAX_RETRIES    = 2          # schema-enforcement retries
OCR_PAGE_DPI   = 150        # DPI for rasterising scanned pages

# ── Document-type keywords (used for auto-detection) ──────────────────────────
ECHALLAN_KEYWORDS = [
    "challan", "echallan", "e-challan", "traffic", "violation",
    "offence", "vehicle", "fine", "registration fee", "cyber treasury",
    "inspector general",
]

NA_PERMISSION_KEYWORDS = [
    "non-agricultural",
    "na permission",
    "iora",              # iORA/ order number prefix
    "prant adhikari",    # signing authority on NA orders
    "final order",       # appears in NA order PDF titles/headings
    "mamlatdar",         # alternative issuing authority
    "non-agriculture",
]

LEASE_DEED_KEYWORDS = [
    "lease deed",
    "lease",
    "lessee",
    "lessor",
    "survey",
    "dhanera",
    "rampura",
    "banaskantha",
]

# ── Extraction schemas ─────────────────────────────────────────────────────────
ECHALLAN_SCHEMA = {
    "challan_number":      "Transaction No (ટ્રોઝેકશન નંબર) — the unique payment reference",
    "vehicle_number":      "Vehicle number — set to N/A if not a traffic challan",
    "violation_date":      "Date from the payment table (DD-MM-YYYY)",
    "amount":              "Total Amount in Rs (numeric only, no currency symbol)",
    "offence_description": "Account Head description (e.g. Registration Fee)",
    "payment_status":      "Paid if Transaction No is present, else Unpaid",
    "survey_number":       "Survey number from Property Details if available",
    "lease_deed_doc_no":   "Lease Deed document/registration number if visible (e.g. 1141/2026)",
    "lease_area":          "Lease area in sq.m. if visible (numeric only)",
    "lease_start_date":    "Date of the e-Challan / registration (DD/MM/YYYY)",
    "village":             "Village name (e.g. Rampura Mota)",
    "echallan_number":     "The e-Challan number (e.g. INGJ260120156942)",
    "valid_up_to":         "Validity date of the e-Challan (DD/MM/YYYY)",
    "tenure_years":        "Lease tenure in years if stated (e.g. 99 Yrs)",
}

NA_PERMISSION_SCHEMA = {
    "survey_number":   "Survey number / block number of the land (e.g. 251/P2)",
    "land_area":       "Total land area as stated in the order (numeric, in sq.m.)",
    "owner_name":      "Full name of the land owner / applicant / lessee",
    "order_date":      "Date of the NA Permission order (DD/MM/YYYY)",
    "authority_name":  "Name and designation of the authority issuing the order "
                       "(e.g. Prant Adhikari, Dhanera)",
    "order_number":    "Full iORA order reference number (e.g. iORA/31/02/112/25/2026)",
    "taluka":          "Taluka where the land is situated",
    "district":        "District where the land is situated",
    "lease_term":      "Lease/permission duration (e.g. 28 years 11 months 0 days)",
    "village":         "Village name (e.g. Rampura Mota)",
}

# ── Consolidated output columns (matching sample output.xlsx — 13 columns) ─────
CONSOLIDATED_COLUMNS = [
    "Sr.no.",
    "Village",
    "Survey No.",
    "Area in NA Order",
    "Dated",
    "NA Order No.",
    "Lease Deed Doc. No.",
    "Lease Area",
    "Lease Start",
    "Tenure",
    "Validity (till)",
    "e-Challan No.",
    "Valid Up to",
]

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")