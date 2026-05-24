from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys

from .categorize import RuleError, categorize_transactions, load_rules
from .credit_card_parser import parse_transactions as parse_credit_card_transactions
from .export import write_csv
from .models import Transaction
from .monthly_summary import write_monthly_summary
from .ocr import OcrError, ocr_pdf
from .parser import parse_transactions as parse_bank_transactions
from .review_report import write_review_report
from .statement_type import is_credit_card_statement
from .suggest_rules import suggest_rule_candidates, write_candidate_yaml


DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class MonthlyRunPaths:
    bank_csv: Path
    bank_ocr: Path
    bank_rule_candidates: Path
    bank_review: Path
    card_csv: Path
    card_ocr: Path
    card_rule_candidates: Path
    card_review: Path
    combined_summary: Path

    def all_outputs(self) -> list[Path]:
        return [
            self.bank_csv,
            self.bank_ocr,
            self.bank_rule_candidates,
            self.bank_review,
            self.card_csv,
            self.card_ocr,
            self.card_rule_candidates,
            self.card_review,
            self.combined_summary,
        ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the monthly bank/card statement workflow from explicit PDF paths."
    )
    parser.add_argument("--bank-pdf", required=True, help="Path to the bank/debit statement PDF.")
    parser.add_argument("--card-pdf", required=True, help="Path to the credit card statement PDF.")
    parser.add_argument("--out-dir", default="outputs", help="Output directory. Default: outputs.")
    parser.add_argument(
        "--rules",
        default=str(Path(__file__).resolve().parents[1] / "rules.yml"),
        help="Path to rules.yml. It is read but never modified.",
    )
    parser.add_argument(
        "--month",
        help="Optional YYYY-MM for the combined monthly summary filename. Defaults to the bank PDF month.",
    )
    parser.add_argument("--lang", default="eng", help="Tesseract OCR language. Default: eng.")
    parser.add_argument("--dpi", type=int, default=250, help="PDF render DPI for OCR.")
    parser.add_argument("--force", action="store_true", help="Overwrite generated outputs if they exist.")
    args = parser.parse_args(argv)

    try:
        paths = build_output_paths(args.bank_pdf, args.card_pdf, args.out_dir, month=args.month)
        _ensure_safe_to_write(paths.all_outputs(), force=args.force)
        rules = load_rules(args.rules)

        bank_transactions = _extract_statement(
            pdf_path=Path(args.bank_pdf),
            csv_path=paths.bank_csv,
            ocr_path=paths.bank_ocr,
            rules=rules,
            language=args.lang,
            dpi=args.dpi,
        )
        card_transactions = _extract_statement(
            pdf_path=Path(args.card_pdf),
            csv_path=paths.card_csv,
            ocr_path=paths.card_ocr,
            rules=rules,
            language=args.lang,
            dpi=args.dpi,
        )

        bank_rows = [transaction.to_csv_row() for transaction in bank_transactions]
        card_rows = [transaction.to_csv_row() for transaction in card_transactions]

        write_candidate_yaml(suggest_rule_candidates(bank_rows, rules), paths.bank_rule_candidates)
        write_candidate_yaml(suggest_rule_candidates(card_rows, rules), paths.card_rule_candidates)
        write_review_report(bank_rows, paths.bank_csv, paths.bank_review)
        write_review_report(card_rows, paths.card_csv, paths.card_review)
        write_monthly_summary([*bank_rows, *card_rows], [paths.bank_csv, paths.card_csv], paths.combined_summary)
    except (OcrError, RuleError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    _print_quality_summary("bank", bank_transactions, paths.bank_csv, paths.bank_ocr, paths.bank_rule_candidates, paths.bank_review)
    _print_quality_summary("card", card_transactions, paths.card_csv, paths.card_ocr, paths.card_rule_candidates, paths.card_review)
    print(f"combined_summary={paths.combined_summary}")
    return 0


def build_output_paths(
    bank_pdf: str | Path,
    card_pdf: str | Path,
    out_dir: str | Path,
    month: str | None = None,
) -> MonthlyRunPaths:
    output_dir = Path(out_dir)
    bank_date = _leading_date(Path(bank_pdf))
    card_date = _leading_date(Path(card_pdf))
    summary_month = _summary_month(month, bank_date)
    return MonthlyRunPaths(
        bank_csv=output_dir / f"{bank_date}.statement.csv",
        bank_ocr=output_dir / f"{bank_date}.ocr.txt",
        bank_rule_candidates=output_dir / f"{bank_date}.rule-candidates.yml",
        bank_review=output_dir / f"{bank_date}.review.md",
        card_csv=output_dir / f"{card_date}.card.statement.csv",
        card_ocr=output_dir / f"{card_date}.card.ocr.txt",
        card_rule_candidates=output_dir / f"{card_date}.card.rule-candidates.yml",
        card_review=output_dir / f"{card_date}.card.review.md",
        combined_summary=output_dir / f"{summary_month}.combined.summary.md",
    )


def _leading_date(path: Path) -> str:
    match = DATE_PREFIX_RE.match(path.name)
    if not match:
        raise ValueError(f"PDF filename must start with YYYY-MM-DD: {path}")
    return match.group(1)


def _summary_month(month: str | None, bank_date: str) -> str:
    if month is None:
        return bank_date[:7]
    if not MONTH_RE.fullmatch(month):
        raise ValueError(f"--month must use YYYY-MM format: {month}")
    return month


def _ensure_safe_to_write(paths: list[Path], force: bool) -> None:
    if force:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        existing_paths = ", ".join(str(path) for path in existing)
        raise ValueError(f"refusing to overwrite existing output(s): {existing_paths}. Use --force to overwrite.")


def _extract_statement(
    *,
    pdf_path: Path,
    csv_path: Path,
    ocr_path: Path,
    rules: list[dict[str, str]],
    language: str,
    dpi: int,
) -> list[Transaction]:
    ocr_text = ocr_pdf(pdf_path, language=language, dpi=dpi)
    ocr_path.parent.mkdir(parents=True, exist_ok=True)
    ocr_path.write_text(ocr_text, encoding="utf-8")

    if is_credit_card_statement(ocr_text):
        transactions = parse_credit_card_transactions(ocr_text)
    else:
        transactions = parse_bank_transactions(ocr_text)
    categorized = categorize_transactions(transactions, rules)
    write_csv(categorized, csv_path)
    return categorized


def _print_quality_summary(
    label: str,
    transactions: list[Transaction],
    csv_path: Path,
    ocr_path: Path,
    rule_candidates_path: Path,
    review_path: Path,
) -> None:
    rows = len(transactions)
    auto_count = sum(1 for transaction in transactions if transaction.status == "auto")
    review_count = sum(1 for transaction in transactions if transaction.status == "review")
    missing_amount_count = sum(
        1 for transaction in transactions if not transaction.money_in and not transaction.money_out
    )
    print(
        f"{label}: rows={rows} auto={auto_count} review={review_count} "
        f"missing_amount={missing_amount_count} csv={csv_path} ocr={ocr_path} "
        f"rule_candidates={rule_candidates_path} review_report={review_path}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
