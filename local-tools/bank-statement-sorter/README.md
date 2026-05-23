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
  --out outputs/rule-candidates.yml
```

The candidate command never updates `rules.yml`. It writes a Git-ignored YAML file for manual review, then you can copy only the rules you want into `rules.yml`.

## Notes

The parser extracts transaction blocks from one transaction start date up to the next transaction start date. `raw_text` contains the complete OCR block used for each row.
