# 📋 Compliance Clerk — Intelligent Document Extraction

An LLM-powered pipeline that automates extraction of key data from heterogeneous Gujarat government PDFs (e-Challan registration receipts and NA Permission orders) into a standardized 13-column Excel report.

## 🎯 Problem

Operations teams manually parse hundreds of legal and government documents daily — slow and error-prone. This tool "reads" scanned and text-based PDFs like a human would and outputs structured data.

## 📄 Supported Document Types

| Type | Example Files | Pages | Content |
|------|--------------|-------|---------|
| **NA Permission** | `251-p2 FINAL ORDER.pdf` | 2–4 (text-based) | iORA non-agricultural permission orders |
| **e-Challan / Lease Deed** | `Rampura Mota S.No.- 251p2 Lease Deed No.- 141.pdf` | 50+ (scanned) | Cyber Treasury registration fee receipts embedded in Lease Deed documents |

## 🏗️ Architecture

```
PDF Input
    │
    ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ Parser       │────▶│ Page Selector │────▶│ OCR Engine  │
│ Factory      │     │ (12/55 pages) │     │ (Gemini     │
│              │     │              │     │  Vision)    │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                    ┌──────────────┐     ┌──────▼──────┐
                    │ Schema       │◀────│ LLM Client  │
                    │ Enforcer     │     │ (Gemini API)│
                    │ (JSON valid.)│     │             │
                    └──────┬───────┘     └─────────────┘
                           │
                    ┌──────▼───────┐
                    │ Excel Writer │────▶ results.xlsx
                    │ (13 columns) │     (1 row per Survey No.)
                    └──────────────┘
```

### Key Components

| Module | Purpose |
|--------|---------|
| `main.py` | CLI entry point with `--file`, `--input-dir`, `--dry-run`, `--show-logs` |
| `config.py` | Schemas, keywords, paths, LLM settings |
| `parsers/` | Auto-detect document type by filename + content sniffing |
| `extractor/llm_client.py` | Gemini API wrapper with rate-limit retry + exponential backoff |
| `extractor/page_selector.py` | Smart page selection (12 of 55 pages for Lease Deeds) |
| `extractor/ocr_engine.py` | Batched Gemini Vision OCR (Gujarati-aware, batch size 2) |
| `extractor/document_extractor.py` | Orchestrator: parse → select → OCR → extract → validate |
| `extractor/schema_enforcer.py` | JSON validation with LLM correction retries |
| `extractor/prompt_builder.py` | Gujarati-aware extraction prompts |
| `output/excel_writer.py` | Merges NA + eChallan records by Survey Number → 13-column Excel |
| `audit/logger.py` | SQLite audit trail for all LLM calls |

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.10+
- A [Gemini API key](https://aistudio.google.com/apikey) (free tier works)

### 2. Install

```bash
git clone <repo-url>
cd compliance-clerk
python -m venv venv
source venv/bin/activate      # Linux/Mac
# venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env and add your API key:
# GEMINI_API_KEY=your_key_here
```

### 4. Run

```bash
# Process a single PDF
python main.py --file data/samples/251-p2\ FINAL\ ORDER.pdf

# Process all PDFs in a directory
python main.py --input-dir data/samples/ --output data/output/results.xlsx

# Dry run (parser detection only, no LLM calls)
python main.py --input-dir data/samples/ --dry-run

# View audit logs
python main.py --show-logs
```

## 📊 Output Format

The pipeline produces a **13-column Excel report** — one row per Survey Number, merging NA Permission and e-Challan data:

| Column | Source |
|--------|--------|
| Sr.no. | Auto-generated |
| Village | NA Permission or eChallan |
| Survey No. | Shared merge key |
| Area in NA Order | NA Permission → `land_area` |
| Dated | NA Permission → `order_date` |
| NA Order No. | NA Permission → `order_number` |
| Lease Deed Doc. No. | eChallan → `lease_deed_doc_no` |
| Lease Area | eChallan → `lease_area` |
| Lease Start | eChallan → `lease_start_date` |
| Tenure | eChallan → `tenure_years` |
| Validity (till) | eChallan → `valid_up_to` |
| e-Challan No. | eChallan → `echallan_number` |
| Valid Up to | eChallan → `valid_up_to` |

## ⚡ Efficiency: Smart Page Selection

Large Lease Deed PDFs (55 pages) are **not** fully OCR'd. The pipeline selects only ~12 key pages:

| Pages | Content |
|-------|---------|
| 1–3 | e-Challan receipt (registration fees, dates) |
| 3–5 | Lease Deed cover + survey details |
| 33–35 | Annexure-I (property description table) |
| 37 | Schedule of Lease Rent |
| 44 | Village Form 9 (7/12 owner details) |
| Last 2 | Sub-Registrar stamps/receipts |

For scanned eChallan pages (pages 1–3), the pipeline sends the **actual page images directly** to Gemini for vision-based extraction — more accurate than OCR→text→extract for Gujarati text.

## 🔒 Audit Trail

Every LLM call is logged to `logs/audit.db` (SQLite):

```
┌────┬────────────────────────┬────────────────────────────┬────┬───────┐
│ ID │ Timestamp              │ File                       │ OK │ ms    │
├────┼────────────────────────┼────────────────────────────┼────┼───────┤
│  1 │ 2026-03-25T13:34:16Z   │ 251-p2 FINAL ORDER.pdf     │ ✓  │ 7232  │
│  2 │ 2026-03-25T13:39:58Z   │ Rampura Mota S.No.- 251p2… │ ✓  │ 28000 │
└────┴────────────────────────┴────────────────────────────┴────┴───────┘
```

View logs anytime with `python main.py --show-logs`.

## ⚙️ Configuration

All settings are in `config.py` or overridable via environment variables:

| Setting | Default | Description |
|---------|---------|-------------|
| `LLM_MODEL` | `gemini-3-flash-preview` | Gemini model to use |
| `GEMINI_API_KEY` | *(required)* | Your Gemini API key |
| `MAX_TOKENS` | `4096` | Max output tokens for LLM responses |
| `MAX_RETRIES` | `2` | Schema enforcement retry count |
| `OCR_PAGE_DPI` | `150` | DPI for rasterising scanned pages |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## 🛠️ Tech Stack

- **LLM**: Google Gemini (via `google-genai` SDK)
- **PDF Parsing**: `pdfplumber` (text extraction + page rasterisation)
- **OCR**: Gemini Vision (batched multi-image calls)
- **Output**: `openpyxl` (styled Excel reports)
- **Audit**: SQLite (full prompt + response logging)
- **Image Processing**: Pillow (PIL)

