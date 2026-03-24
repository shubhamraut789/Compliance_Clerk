"""
config.py
Central configuration for the Compliance Clerk pipeline.
All schema definitions, model settings, and path constants live here.
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
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.0-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MAX_TOKENS     = 1500
MAX_RETRIES    = 2          # schema-enforcement retries
OCR_PAGE_DPI   = 150        # DPI for rasterising scanned pages

# ── Document-type keywords (used for auto-detection) ──────────────────────────
ECHALLAN_KEYWORDS = ["challan", "echallan", "e-challan", "traffic", "violation",
                     "offence", "vehicle", "fine"]
LEASE_DEED_KEYWORDS = ["lease", "deed", "lessee", "lessor", "survey", "na order",
                        "non-agricultural", "rampura", "banaskantha"]

# ── Extraction schemas ─────────────────────────────────────────────────────────
# Each schema maps output column name → description for the LLM.

ECHALLAN_SCHEMA = {
    "challan_number":      "The unique challan / violation reference number",
    "vehicle_number":      "Vehicle registration plate number",
    "violation_date":      "Date of the violation (YYYY-MM-DD if possible)",
    "amount":              "Fine / penalty amount in INR (numeric only, no currency symbol)",
    "offence_description": "Brief description of the traffic offence",
    "payment_status":      "Payment status (e.g. Paid / Unpaid / Pending)",
}

LEASE_DEED_SCHEMA = {
    "village":             "Village name where the land is situated",
    "survey_number":       "New survey number of the subject land",
    "area_in_na_order":    "Area of land as per the NA Order (numeric, in SQM or Acres as stated)",
    "dated":               "Date of the NA Order (DD/MM/YYYY)",
    "na_order_number":     "NA Order / iORA reference number",
    "lease_deed_doc_no":   "Lease Deed document / registration number (e.g. 837/2025)",
    "lease_area":          "Total lease area in SQM (numeric only)",
    "lease_start_date":    "Date the lease deed was executed / registered (DD/MM/YYYY)",
    "owner_name":          "Full name of the Lessor / land owner",
    "lessee_name":         "Full name of the Lessee / company taking the lease",
    "taluka":              "Taluka where the land is situated",
    "district":            "District where the land is situated",
    "lease_term_years":    "Lease term in years",
}

# ── Excel output column order ──────────────────────────────────────────────────
ECHALLAN_COLUMNS = [
    "sr_no", "source_file",
    "challan_number", "vehicle_number", "violation_date",
    "amount", "offence_description", "payment_status",
]

LEASE_DEED_COLUMNS = [
    "sr_no", "source_file",
    "village", "survey_number", "area_in_na_order", "dated",
    "na_order_number", "lease_deed_doc_no", "lease_area",
    "lease_start_date", "owner_name", "lessee_name",
    "taluka", "district", "lease_term_years",
]

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")