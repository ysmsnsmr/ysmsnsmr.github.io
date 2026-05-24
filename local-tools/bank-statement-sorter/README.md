# Bank Statement Sorter CLI

Local-only CLI MVP for OCRing a Malaysian bank statement PDF, extracting transaction blocks, categorizing them with editable rules, and exporting CSV.

No PDF, OCR text, or CSV output should be committed. The repository `.gitignore` excludes the local data and output paths for this tool.

## Setup

Install local OCR:

```sh
brew install tesseract
```

Create a Python environment and install dependencies:

```sh
cd local-tools/bank-statement-sorter
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

```sh
.venv/bin/python -m statement_sorter /path/to/statement.pdf --out outputs/statement.csv
```

Optional flags:

```sh
.venv/bin/python -m statement_sorter /path/to/statement.pdf \
  --out outputs/statement.csv \
  --rules rules.yml \
  --ocr-text outputs/debug.ocr.txt
```

CSV columns are always:

```text
date, description, money_in, money_out, balance, category, treatment, status, raw_text
```

`status` is `auto` only when a rule matched and the parser did not mark the block as uncertain. Otherwise it is `review`.

## Normal operation

Run commands from the tool directory:

```sh
cd local-tools/bank-statement-sorter
```

Extract a bank/debit statement:

```sh
.venv/bin/python -m statement_sorter /path/to/2026-05-06_Statement.pdf \
  --out outputs/2026-05-06.statement.csv \
  --ocr-text outputs/2026-05-06.ocr.txt
```

Extract a credit card statement with a `.card.` filename prefix:

```sh
.venv/bin/python -m statement_sorter /path/to/2026-05-21_Statement.pdf \
  --out outputs/2026-05-21.card.statement.csv \
  --ocr-text outputs/2026-05-21.card.ocr.txt
```

The CLI auto-detects supported HSBC credit card OCR and uses the credit card parser. Credit card rows use the same CSV schema: normal charges go to `money_out`, `CR` rows go to `money_in`, and `balance` is empty.

## Rules

Rules are evaluated from top to bottom. `pattern` is matched case-insensitively against both `description` and `raw_text`.

```yaml
rules:
  - pattern: "SALARY"
    category: "Income"
    treatment: "income"
```

Allowed `treatment` values:

```text
expense, income, transfer, fee, cash, unknown
```

## Rule candidates

To grow `rules.yml`, generate candidates from a local CSV output:

```sh
.venv/bin/python -m statement_sorter.suggest_rules \
  outputs/2026-05-06.statement.csv \
  --out outputs/2026-05-06.rule-candidates.yml
```

The candidate command never updates `rules.yml`. It writes a Git-ignored YAML file for manual review, then you can copy only the rules you want into `rules.yml`.

For credit card CSVs:

```sh
.venv/bin/python -m statement_sorter.suggest_rules \
  outputs/2026-05-21.card.statement.csv \
  --out outputs/2026-05-21.card.rule-candidates.yml
```

Review candidates manually before editing `rules.yml`. Add only confirmed reusable merchant or payee patterns. Do not add personal-name QR payments unless they are confirmed transfers, page or statement artifacts, card text, OCR debris, transaction IDs, or over-specific reference strings.

## Reports

Generate a privacy-safe review report:

```sh
.venv/bin/python -m statement_sorter.review_report \
  outputs/2026-05-21.card.statement.csv \
  --out outputs/2026-05-21.card.review.md
```

Generate a monthly summary:

```sh
.venv/bin/python -m statement_sorter.monthly_summary \
  outputs/2026-05-21.card.statement.csv \
  --out outputs/2026-05-21.card.summary.md
```

Generate a combined monthly summary from multiple CSVs:

```sh
.venv/bin/python -m statement_sorter.monthly_summary \
  outputs/2026-05-06.statement.csv \
  outputs/2026-05-21.card.statement.csv \
  --out outputs/2026-05.combined.summary.md
```

Reports do not render `raw_text`. They include descriptions only where useful for review or top-expense display.

## Recommended run order

1. Extract the statement CSV and optional OCR text into `outputs/`.
2. Generate rule candidates from the CSV.
3. Manually copy only confirmed candidates into `rules.yml`.
4. Re-run extraction so the updated rules are applied.
5. Regenerate rule candidates and confirm only expected review rows remain.
6. Generate review and monthly summary reports.
7. Inspect remaining `review`, `Other`, `unknown`, and missing-amount rows.

## Past statement backfill and rule hardening

Backfill old statements gradually. Start with only one or two past months, with one bank/debit PDF and one credit card PDF per month. The goal is not to perfectly classify all historical data at once. Use the run to check parser stability across months, grow safe reusable rules, collect missing-amount and review patterns, and identify parser fixes that repeat across multiple months.

For each month, run the same local flow:

```sh
.venv/bin/python -m statement_sorter /path/to/bank.pdf \
  --out outputs/YYYY-MM-DD.statement.csv \
  --ocr-text outputs/YYYY-MM-DD.ocr.txt

.venv/bin/python -m statement_sorter /path/to/card.pdf \
  --out outputs/YYYY-MM-DD.card.statement.csv \
  --ocr-text outputs/YYYY-MM-DD.card.ocr.txt

.venv/bin/python -m statement_sorter.suggest_rules \
  outputs/YYYY-MM-DD.statement.csv \
  --out outputs/YYYY-MM-DD.rule-candidates.yml

.venv/bin/python -m statement_sorter.suggest_rules \
  outputs/YYYY-MM-DD.card.statement.csv \
  --out outputs/YYYY-MM-DD.card.rule-candidates.yml

.venv/bin/python -m statement_sorter.review_report \
  outputs/YYYY-MM-DD.statement.csv \
  --out outputs/YYYY-MM-DD.review.md

.venv/bin/python -m statement_sorter.review_report \
  outputs/YYYY-MM-DD.card.statement.csv \
  --out outputs/YYYY-MM-DD.card.review.md

.venv/bin/python -m statement_sorter.monthly_summary \
  outputs/YYYY-MM-DD.statement.csv \
  outputs/YYYY-MM-DD.card.statement.csv \
  --out outputs/YYYY-MM.combined.summary.md
```

Review these quality metrics after each run:

```sh
.venv/bin/python - <<'PY'
import csv
from collections import Counter

paths = [
    "outputs/YYYY-MM-DD.statement.csv",
    "outputs/YYYY-MM-DD.card.statement.csv",
]

for path in paths:
    print("\n==", path, "==")
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    print("transactions:", len(rows))
    print("status:", Counter(row.get("status", "") for row in rows))
    print("treatment:", Counter(row.get("treatment", "") for row in rows))
    print("category:", Counter(row.get("category", "") for row in rows))
    print("missing amount:", sum(1 for row in rows if not row.get("money_in") and not row.get("money_out")))
    print("balance nonempty:", sum(1 for row in rows if row.get("balance")))
PY
```

For bank/debit CSVs, check transactions, `auto` vs `review`, treatment/category distribution, missing amount, and nonempty balance count. For credit card CSVs, missing amount should normally be `0`, and `balance` should normally be empty for every row.

For combined summaries, check that `Living Balance` is not extreme, `Transfer Out` contains card payments, account movement, and brokerage transfers instead of living expenses, `Unknown Out` is small enough to trust the report, and card payments are not mixed into `expense`.

Only add confirmed reusable merchant or payee patterns to `rules.yml`, such as stable grocery, dining, utilities, telco, or subscription names. Do not add personal names with unclear meaning, OCR noise, transaction IDs, one-off long strings, page/card artifacts, or candidates that only appeared in missing-amount rows.

Treat parser changes conservatively. A one-off OCR failure should usually remain a review item. Open a parser follow-up only when the same failure pattern repeats across two or three months.

## Notes

The bank/debit parser extracts transaction blocks from one transaction start date up to the next transaction start date. `raw_text` contains the complete OCR block used for each row.

`outputs/` is Git-ignored. Do not commit PDFs, OCR text, CSVs, candidate YAML files, or generated Markdown reports.

Monthly summaries accept one or more statement CSVs. Multiple inputs are combined without deduplication, so pass each statement CSV only once.
