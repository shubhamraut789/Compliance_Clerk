"""
main.py
CLI entry point for the Compliance Clerk pipeline.

Usage examples:
  python main.py --file data/samples/deed.pdf
  python main.py --input-dir data/samples/
  python main.py --input-dir data/samples/ --output data/output/results.xlsx
  python main.py --file deed.pdf --dry-run
  python main.py --show-logs
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# ── Bootstrap: ensure project root is on sys.path ─────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import OUTPUT_DIR, LOG_LEVEL
from extractor.document_extractor import DocumentExtractor
from output.excel_writer import ExcelWriter
from audit.logger import AuditLogger


# ── Logging setup ──────────────────────────────────────────────────────────────

def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


# ── File discovery ─────────────────────────────────────────────────────────────

def collect_pdfs(args) -> list:
    """Collect all PDF paths to process."""
    paths = []
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"ERROR: File not found: {p}")
            sys.exit(1)
        paths = [p]
    elif args.input_dir:
        d = Path(args.input_dir)
        if not d.is_dir():
            print(f"ERROR: Directory not found: {d}")
            sys.exit(1)
        paths = sorted(d.glob("*.pdf"))
        if not paths:
            print(f"No PDFs found in {d}")
            sys.exit(0)
    return paths


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run_pipeline(args) -> None:
    logger = logging.getLogger("main")

    # API key
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key and not args.dry_run:
        print("WARNING: GEMINI_API_KEY not set. Set it in .env or environment.")
        print("         The pipeline will fail when trying to call the LLM.")

    paths = collect_pdfs(args)
    logger.info("Found %d PDF(s) to process", len(paths))

    if args.dry_run:
        print("\n=== DRY RUN — showing extracted text only (no LLM calls) ===\n")
        for p in paths:
            from parsers import get_parser
            parser = get_parser(str(p))
            doc = parser.load()
            print(f"\n{'='*60}")
            print(f"FILE : {p.name}")
            print(f"TYPE : {doc.doc_type}")
            print(f"PAGES: {len(doc.pages)}")
            scanned = sum(1 for pg in doc.pages if pg.is_scanned)
            print(f"SCANNED PAGES: {scanned}")
            print(f"TEXT PREVIEW:\n{doc.full_text[:800]}")
        return

    # Normal run — extract with LLM
    extractor = DocumentExtractor(api_key=api_key)
    writer    = ExcelWriter()
    results   = []

    for i, pdf_path in enumerate(paths, start=1):
        print(f"[{i}/{len(paths)}] Processing: {pdf_path.name} ...", end=" ", flush=True)
        try:
            record = extractor.process(str(pdf_path))
            writer.add(record)
            results.append(record)
            status = "ERROR" if record.get("_error") else "OK"
            print(status)
        except Exception as exc:
            print(f"FAILED ({exc})")
            logger.exception("Unhandled error for %s", pdf_path.name)

    # Output path
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.output or str(OUTPUT_DIR / f"output_{ts}.xlsx")
    writer.save(out_path)

    # Summary
    summary = writer.summary()
    audit   = AuditLogger().summary()
    print(f"\n{'='*55}")
    print(f"  PDFs processed  : {len(paths)}")
    print(f"  NA Permissions  : {summary['na_permissions']}")
    print(f"  eChallans       : {summary['echallans']}")
    print(f"  Errors          : {summary['errors']}")
    print(f"  LLM calls       : {audit['total']} (ok={audit['parsed_ok']}, failed={audit['failed']})")
    print(f"  Output          : {out_path}")
    print(f"{'='*55}\n")


def show_logs(n: int = 20) -> None:
    """Print recent LLM audit log entries."""
    audit = AuditLogger()
    rows = audit.get_recent(n)
    if not rows:
        print("No audit logs found.")
        return
    print(f"\n{'='*70}")
    print(f"{'ID':<5} {'Timestamp':<22} {'File':<30} {'OK':<5} {'ms':<6}")
    print(f"{'-'*70}")
    for r in rows:
        ok = "✓" if r["parsed_ok"] else "✗"
        print(f"{r['id']:<5} {r['timestamp']:<22} {r['file_name'][:28]:<30} {ok:<5} {r['duration_ms'] or 0:<6}")
    print(f"{'='*70}\n")
    summary = audit.summary()
    print(f"Total: {summary['total']}  OK: {summary['parsed_ok']}  Failed: {summary['failed']}\n")


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compliance Clerk — LLM-powered document extraction pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument("--file",      metavar="PATH", help="Process a single PDF file")
    group.add_argument("--input-dir", metavar="DIR",  help="Process all PDFs in a directory")
    p.add_argument("--output",    metavar="PATH", help="Output Excel file path")
    p.add_argument("--dry-run",   action="store_true", help="Extract text only, no LLM calls")
    p.add_argument("--show-logs", action="store_true", help="Show recent LLM audit log entries")
    p.add_argument("--log-level", default=LOG_LEVEL, help="Logging level (default: INFO)")
    return p


def main() -> None:
    cli = build_parser()
    args = cli.parse_args()

    setup_logging(args.log_level)

    if args.show_logs:
        show_logs()
        return

    if not args.file and not args.input_dir:
        cli.print_help()
        sys.exit(0)

    run_pipeline(args)


if __name__ == "__main__":
    main()