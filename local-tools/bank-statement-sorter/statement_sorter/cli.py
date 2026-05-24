from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .categorize import RuleError, categorize_transactions, load_rules
from .credit_card_parser import parse_transactions as parse_credit_card_transactions
from .export import write_csv
from .ocr import OcrError, ocr_pdf
from .parser import parse_transactions as parse_bank_transactions
from .statement_type import is_credit_card_statement


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OCR a local bank statement PDF, categorize transactions, and export CSV."
    )
    parser.add_argument("pdf", help="Path to the local bank statement PDF.")
    parser.add_argument("--out", required=True, help="CSV output path.")
    parser.add_argument(
        "--rules",
        default=str(Path(__file__).resolve().parents[1] / "rules.yml"),
        help="Path to rules.yml.",
    )
    parser.add_argument(
        "--ocr-text",
        help="Optional debug path for the full OCR text. Do not commit this file.",
    )
    parser.add_argument("--lang", default="eng", help="Tesseract OCR language. Default: eng.")
    parser.add_argument("--dpi", type=int, default=250, help="PDF render DPI for OCR.")

    args = parser.parse_args(argv)

    try:
        rules = load_rules(args.rules)
        ocr_text = ocr_pdf(args.pdf, language=args.lang, dpi=args.dpi)
        if args.ocr_text:
            ocr_path = Path(args.ocr_text)
            ocr_path.parent.mkdir(parents=True, exist_ok=True)
            ocr_path.write_text(ocr_text, encoding="utf-8")

        if is_credit_card_statement(ocr_text):
            transactions = parse_credit_card_transactions(ocr_text)
        else:
            transactions = parse_bank_transactions(ocr_text)
        categorized = categorize_transactions(transactions, rules)
        write_csv(categorized, args.out)
    except (OcrError, RuleError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    review_count = sum(1 for transaction in categorized if transaction.status == "review")
    print(f"Wrote {len(categorized)} transactions to {args.out}. Review needed: {review_count}.")
    return 0
