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
NA_PERMISSION_KEYWORDS = ["non-agricultural", "na permission", "na order", "iora",
                          "survey", "mamlatdar", "taluka", "district"]
LEASE_DEED_KEYWORDS = ["lease deed", "lease", "lessee", "lessor", "survey",
                       "dhanera", "rampura", "banaskantha"]
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

NA_PERMISSION_SCHEMA = {
    "survey_number":       "Survey number of the land / property",
    "land_area":           "Total land area (numeric, in SQM or as stated in document)",
    "owner_name":          "Full name of the land owner / applicant",
    "order_date":          "Date of the NA Permission order (DD/MM/YYYY)",
    "authority_name":      "Name of the authority issuing the permission",
    "order_number":        "Reference number or order number of the NA Permission",
    "taluka":              "Taluka where the land is situated",
    "district":            "District where the land is situated",
    "na_order_number":     "NA Order reference number if applicable",
}

LEASE_DEED_SCHEMA = {
    "survey_number":       "Survey number / plot number of the land (e.g. 251/P2)",
    "land_area":           "Total land area (numeric, in SQM or Acres as stated)",
    "owner_name":          "Full name of the Lessor / land owner",
    "lessee_name":         "Full name of the Lessee / company taking the lease",
    "taluka":              "Taluka where the land is situated",
    "district":            "District where the land is situated",
    "lease_start_date":    "Date the lease deed was executed / registered (DD/MM/YYYY)",
    "lease_term_years":    "Lease term in years",
    "lease_deed_doc_no":   "Lease Deed document / registration number",
}

# ── Excel output column order ──────────────────────────────────────────────────
ECHALLAN_COLUMNS = [
    "sr_no", "source_file",
    "challan_number", "vehicle_number", "violation_date",
    "amount", "offence_description", "payment_status",
]

NA_PERMISSION_COLUMNS = [
    "sr_no", "source_file",
    "survey_number", "land_area", "owner_name", "order_date",
    "authority_name", "order_number", "taluka", "district", "na_order_number",
]

LEASE_DEED_COLUMNS = [
    "sr_no", "source_file",
     "survey_number", "land_area", "owner_name", "lessee_name",
    "taluka", "district", "lease_start_date", "lease_term_years", "lease_deed_doc_no",
]

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")