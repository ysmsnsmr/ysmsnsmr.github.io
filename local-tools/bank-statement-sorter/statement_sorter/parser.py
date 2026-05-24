from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, InvalidOperation
import re

from .models import Transaction


MONTHS = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}

NUMERIC_DATE_RE = re.compile(r"(?<![A-Za-z0-9])([0O]?\d{1,2})[/-]([0O]?\d{1,2})(?:[/-]([0O]?\d{2,4}))?(?![A-Za-z0-9])")
TEXT_DATE_RE = re.compile(
    r"(?<![A-Za-z0-9])([0O]?\d{1,2})\s*("
    + "|".join(MONTHS)
    + r")[A-Z]*\s*(?:[/-]?\s*(\d{2,4}))?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
AMOUNT_RE = re.compile(r"(?<!\w)(?:RM\s*)?([+-]?\(?\d[\d,]*\.\d{2}\)?)(?!\w)")
BALANCE_TOLERANCE = Decimal("0.01")
TRANSACTION_START_PREFIX_RE = re.compile(r"^[\s|()_=~§/]*")
NON_TRANSACTION_START_PHRASES = (
    "STATEMENT DATE",
    "CUSTOMER NUMBER",
    "SEQUENCE NUMBER",
    "SUMMARY OF YOUR PORTFOLIO",
    "DEPOSITS AND INVESTMENTS",
    "TOTAL DEPOSITS",
    "ACCOUNT NUMBER",
    "BALANCE BROUGHT FORWARD",
    "BALANCE CARRIED FORWARD",
    "CLOSING BALANCE",
)
BLOCK_BOUNDARY_ARTIFACT_PHRASES = (
    "BALANCE BROUGHT FORWARD",
    "BALANCE BROUGHTFORWARD",
    "BALANCE CARRIED FORWARD",
    "BALANCE CARRIEDFORWARD",
    "STATEMENT DETAILS",
    "TRANSACTION TURNOVER",
    "TRANSACTION COUNT",
    "PROTECTED BY PIDM UP TO",
    "AMANAH ADVANCE A/C-I",
)
FOOTER_HARD_STOP_PHRASES = (
    "END OF STATEMENT",
    "IMPORTANT NOTES",
    "NOTA PENTING",
    "TERMS AND CONDITIONS",
    "PIDM",
    "UNIVERSAL TERMS AND CONDITIONS",
)
ACCOUNT_SUMMARY_MARKERS = (
    "DEMAND DEPOSITS",
    "CREDIT/CHARGE",
    "DR=DEBIT",
    "TOTAL DEPOSITS",
    "TOTAL DEPOSITS AND INVESTMENTS",
)
TRANSACTION_MARKER_RE = re.compile(
    r"QR PAYMENT|VISA POS|FPX-|JOMPAY|MEPS-|SALARY|TAX_REFUND|CRE CARD PAYMENT|GLOBAL MONEY TRANSFER",
    re.IGNORECASE,
)


def parse_transactions(ocr_text: str) -> list[Transaction]:
    blocks = split_transaction_blocks(ocr_text)
    previous_balance = _find_balance_brought_forward(ocr_text)
    transactions: list[Transaction] = []

    for block in blocks:
        parent_date = _parse_transaction_start_date(block[0])
        for chunk in _split_sub_transaction_chunks(block):
            transaction = _parse_block(chunk, previous_balance, parent_date)
            if transaction is None:
                continue
            transactions.append(transaction)
            balance = _amount_to_decimal(transaction.balance)
            if balance is not None:
                previous_balance = balance

    return transactions


def split_transaction_blocks(ocr_text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []

    for raw_line in ocr_text.splitlines():
        line = _clean_line(raw_line)
        if not line:
            continue
        if _is_footer_hard_stop_line(line):
            if current:
                blocks.append(current)
                current = []
            break
        if _is_block_boundary_artifact_line(line):
            continue
        if _is_non_transaction_start_line(line):
            continue
        if _parse_transaction_start_date(line):
            if current:
                blocks.append(current)
            current = [line]
            continue
        if current:
            current.append(line)

    if current:
        blocks.append(current)
    return blocks


def _split_sub_transaction_chunks(lines: list[str]) -> list[list[str]]:
    cleaned_lines = [
        line
        for line in lines
        if not _is_non_transaction_start_line(line) and not _looks_like_table_header(line)
    ]
    if not cleaned_lines:
        return []

    chunks: list[list[str]] = []
    current: list[str] = []
    marker_seen = False

    for line in cleaned_lines:
        has_marker = _has_transaction_marker(line)
        if has_marker and marker_seen and current:
            chunks.append(current)
            current = [line]
        else:
            current.append(line)
        if has_marker:
            marker_seen = True

    if current:
        chunks.append(current)
    return chunks


def _parse_block(
    lines: list[str], previous_balance: Decimal | None = None, parent_date: str | None = None
) -> Transaction | None:
    if _is_non_transaction_start_line(lines[0]):
        return None

    date = _parse_transaction_start_date(lines[0]) or parent_date
    if not date:
        return None

    raw_text = "\n".join(lines)
    if _is_account_summary_block(raw_text):
        return None

    amount_matches = list(AMOUNT_RE.finditer(raw_text))
    amounts = [_normalize_amount(match.group(1)) for match in amount_matches]
    amount_values = [_amount_to_decimal(amount) for amount in amounts]
    review_reasons: list[str] = []

    balance = ""
    amount = ""
    money_in = ""
    money_out = ""
    if not amounts:
        review_reasons.append("no_amount")
    else:
        balance = amounts[-1]
        balance_value = amount_values[-1]
        inferred = _infer_amount_from_running_balance(
            amounts,
            amount_values,
            previous_balance,
            balance_value,
        )
        if inferred:
            direction, amount = inferred
            if direction == "out":
                money_out = amount
            else:
                money_in = amount
        else:
            review_reasons.append("no_confident_amount")

    description = _extract_description(lines, amount_matches)
    if not description:
        review_reasons.append("missing_description")

    transaction = Transaction(
        date=date,
        description=description,
        money_in=money_in,
        money_out=money_out,
        balance=balance,
        raw_text=raw_text,
        amount=amount,
        review_reasons=tuple(review_reasons),
    )
    return _apply_explicit_dr_cr(transaction, raw_text)


def _apply_explicit_dr_cr(transaction: Transaction, raw_text: str) -> Transaction:
    if not transaction.amount:
        return transaction
    amount_pattern = re.escape(transaction.amount)
    compact = raw_text.replace(",", "")
    normalized_amount = transaction.amount.replace(",", "")
    if re.search(rf"{amount_pattern}\s*CR\b|\bCR\s*{amount_pattern}", raw_text, re.IGNORECASE):
        return replace(
            transaction,
            money_in=transaction.amount,
            money_out="",
            review_reasons=_without_uncertain_amount_direction(transaction.review_reasons),
        )
    if re.search(rf"{amount_pattern}\s*DR\b|\bDR\s*{amount_pattern}", raw_text, re.IGNORECASE):
        return replace(
            transaction,
            money_in="",
            money_out=transaction.amount,
            review_reasons=_without_uncertain_amount_direction(transaction.review_reasons),
        )
    if re.search(rf"{re.escape(normalized_amount)}\s*CR\b|\bCR\s*{re.escape(normalized_amount)}", compact, re.IGNORECASE):
        return replace(
            transaction,
            money_in=transaction.amount,
            money_out="",
            review_reasons=_without_uncertain_amount_direction(transaction.review_reasons),
        )
    if re.search(rf"{re.escape(normalized_amount)}\s*DR\b|\bDR\s*{re.escape(normalized_amount)}", compact, re.IGNORECASE):
        return replace(
            transaction,
            money_in="",
            money_out=transaction.amount,
            review_reasons=_without_uncertain_amount_direction(transaction.review_reasons),
        )
    return transaction


def _without_uncertain_amount_direction(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(reason for reason in reasons if reason != "uncertain_amount_direction")


def _infer_amount_from_running_balance(
    amounts: list[str],
    amount_values: list[Decimal | None],
    previous_balance: Decimal | None,
    balance: Decimal | None,
) -> tuple[str, str] | None:
    if previous_balance is None or balance is None or len(amounts) < 2:
        return None

    candidates = list(zip(amounts[:-1], amount_values[:-1], strict=True))
    withdrawal_delta = previous_balance - balance
    deposit_delta = balance - previous_balance

    withdrawal = _find_matching_amount(candidates, withdrawal_delta)
    if withdrawal:
        return "out", withdrawal

    deposit = _find_matching_amount(candidates, deposit_delta)
    if deposit:
        return "in", deposit

    return None


def _find_matching_amount(
    candidates: list[tuple[str, Decimal | None]], delta: Decimal
) -> str | None:
    if delta < Decimal("0"):
        return None
    for amount, value in candidates:
        if value is not None and abs(value - delta) <= BALANCE_TOLERANCE:
            return amount
    return None


def _extract_description(lines: list[str], amount_matches: list[re.Match[str]]) -> str:
    raw_text = "\n".join(lines)
    ranges = [(match.start(), match.end()) for match in amount_matches]
    chars = list(raw_text)
    for start, end in ranges:
        for index in range(start, end):
            chars[index] = " "
    without_amounts = "".join(chars)
    without_date = _remove_leading_date(without_amounts)
    parts = [_clean_line(part) for part in without_date.splitlines()]
    parts = [part for part in parts if part and not _looks_like_table_header(part)]
    return " ".join(parts)


def _remove_leading_date(text: str) -> str:
    found = _find_date(text)
    if found is None:
        return text.strip()

    _, match = found
    without_date = f"{text[:match.start()]} {text[match.end():]}"
    return re.sub(r"^[\s_\-|/{}()[\]]+", "", without_date).strip()


def _parse_date(line: str) -> str | None:
    found = _find_date(line)
    if found is None:
        return None
    return found[0]


def _parse_transaction_start_date(line: str) -> str | None:
    if _is_non_transaction_start_line(line):
        return None

    match_start = TRANSACTION_START_PREFIX_RE.match(line)
    search_from = match_start.end() if match_start else 0
    candidate = line[search_from:]
    found = _find_date(candidate)
    if found is None:
        return None

    _, match = found
    if match.start() != 0:
        return None
    return found[0]


def _find_date(line: str) -> tuple[str, re.Match[str]] | None:
    for match in TEXT_DATE_RE.finditer(line):
        parsed = _date_from_text_match(match)
        if parsed:
            return parsed, match

    for match in NUMERIC_DATE_RE.finditer(line):
        parsed = _date_from_numeric_match(match)
        if parsed:
            return parsed, match

    return None


def _date_from_text_match(match: re.Match[str]) -> str | None:
    day_text, month_name, year = match.groups()
    day = _parse_ocr_number(day_text)
    if day is None or not 1 <= day <= 31:
        return None

    month = MONTHS[month_name[:3].upper()]
    if year:
        normalized_year = _normalize_year(year)
        if normalized_year is None:
            return None
        return f"{normalized_year}-{month}-{day:02d}"
    return f"--{month}-{day:02d}"


def _date_from_numeric_match(match: re.Match[str]) -> str | None:
    day_text, month_text, year = match.groups()
    day = _parse_ocr_number(day_text)
    month = _parse_ocr_number(month_text)
    if day is None or month is None or not 1 <= day <= 31 or not 1 <= month <= 12:
        return None

    if year:
        normalized_year = _normalize_year(year)
        if normalized_year is None:
            return None
        return f"{normalized_year}-{month:02d}-{day:02d}"
    return f"--{month:02d}-{day:02d}"


def _parse_ocr_number(value: str) -> int | None:
    normalized = value.replace("O", "0").replace("o", "0")
    if not normalized.isdigit():
        return None
    return int(normalized)


def _normalize_year(year: str) -> str | None:
    year = year.replace("O", "0").replace("o", "0")
    if not year.isdigit():
        return None
    if len(year) == 2:
        return f"20{year}"
    if len(year) != 4:
        return None
    return year


def _normalize_amount(amount: str) -> str:
    amount = amount.strip()
    negative = amount.startswith("(") and amount.endswith(")")
    amount = amount.strip("()")
    if negative and not amount.startswith("-"):
        amount = f"-{amount}"
    return amount


def _amount_to_decimal(amount: str) -> Decimal | None:
    if not amount:
        return None
    normalized = amount.strip().replace(",", "")
    negative = normalized.startswith("(") and normalized.endswith(")")
    normalized = normalized.strip("()")
    if negative and not normalized.startswith("-"):
        normalized = f"-{normalized}"
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _find_balance_brought_forward(ocr_text: str) -> Decimal | None:
    for raw_line in ocr_text.splitlines():
        line = _clean_line(raw_line)
        if "BALANCE BROUGHT FORWARD" not in line.upper():
            continue
        amount_matches = list(AMOUNT_RE.finditer(line))
        if not amount_matches:
            continue
        amount = _normalize_amount(amount_matches[-1].group(1))
        balance = _amount_to_decimal(amount)
        if balance is not None:
            return balance
    return None


def _looks_like_table_header(line: str) -> bool:
    lower = line.lower()
    header_words = ["date", "description", "withdrawal", "deposit", "balance"]
    return sum(1 for word in header_words if word in lower) >= 2


def _is_non_transaction_start_line(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line).strip().upper()
    return any(phrase in normalized for phrase in NON_TRANSACTION_START_PHRASES)


def _is_block_boundary_artifact_line(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line).strip().upper()
    return (
        any(phrase in normalized for phrase in BLOCK_BOUNDARY_ARTIFACT_PHRASES)
        or re.match(r"^PAGE(?:\b|\s+\d)", normalized) is not None
    )


def _is_footer_hard_stop_line(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line).strip().upper()
    if "PROTECTED BY PIDM UP TO" in normalized:
        return False
    return any(phrase in normalized for phrase in FOOTER_HARD_STOP_PHRASES)


def _is_account_summary_block(raw_text: str) -> bool:
    normalized = re.sub(r"\s+", " ", raw_text).strip().upper()
    return any(marker in normalized for marker in ACCOUNT_SUMMARY_MARKERS)


def _has_transaction_marker(line: str) -> bool:
    return bool(TRANSACTION_MARKER_RE.search(line))


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()
