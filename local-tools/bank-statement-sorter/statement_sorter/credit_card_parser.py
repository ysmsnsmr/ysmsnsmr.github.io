from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from .models import Transaction


MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

DATE_TOKEN_RE = r"([0O]?\d{1,2})\s*(" + "|".join(MONTHS) + r")[A-Z]*"
STATEMENT_DATE_RE = re.compile(r"STATEMENT\s+DATE\s+" + DATE_TOKEN_RE + r"\s*(\d{2,4})", re.IGNORECASE)
ANY_YEAR_DATE_RE = re.compile(DATE_TOKEN_RE + r"\s*(\d{4})", re.IGNORECASE)
TRANSACTION_LINE_RE = re.compile(
    r"^\s*"
    + DATE_TOKEN_RE
    + r"\s+"
    + DATE_TOKEN_RE
    + r"\s+"
    + r"(?P<body>.+?)\s+"
    + r"(?P<amount>[+-]?\(?\d[\d,]*\.\d{2}\)?)(?P<cr>\s*CR)?\s*$",
    re.IGNORECASE,
)

NON_TRANSACTION_PHRASES = (
    "ACCOUNT STATEMENT",
    "CARD NUMBER",
    "STATEMENT DATE",
    "PAYMENT DUE DATE",
    "MINIMUM MONTHLY PAYMENT",
    "PREVIOUS STATEMENT BALANCE",
    "CREDIT LIMIT",
    "CREDIT LIMIT USED",
    "STATEMENT BALANCE",
    "CASH BACK SUMMARY",
    "TOTAL CASH BACK BALANCE",
    "TOTAL CREDIT LIMIT USED",
    "YOUR CHARGE(S) FOR THIS MONTH",
    "POST DATE",
    "TRANSACTION DATE",
    "TRANSACTION DETAILS",
    "PAYMENT ALLOCATION STATEMENT",
    "PLEASE CHECK",
    "IF YOU MAKE",
    "IF NO DISCREPANCY",
)


@dataclass(frozen=True)
class _CreditCardRow:
    post_month: int
    transaction_day: int
    transaction_month: int
    description: str
    amount: str
    is_credit: bool
    raw_text: str


def parse_transactions(ocr_text: str) -> list[Transaction]:
    statement_year, statement_month = _find_statement_year_month(ocr_text)
    rows = _split_credit_card_rows(ocr_text)
    transactions: list[Transaction] = []

    for row in rows:
        transaction_date = _format_transaction_date(
            row.transaction_day,
            row.transaction_month,
            statement_year,
            statement_month,
        )
        if transaction_date is None:
            continue

        review_reasons: list[str] = []
        if not row.description:
            review_reasons.append("missing_description")

        transactions.append(
            Transaction(
                date=transaction_date,
                description=row.description,
                money_in=row.amount if row.is_credit else "",
                money_out="" if row.is_credit else row.amount,
                balance="",
                raw_text=row.raw_text,
                amount=row.amount,
                review_reasons=tuple(review_reasons),
            )
        )

    return transactions


def _split_credit_card_rows(ocr_text: str) -> list[_CreditCardRow]:
    rows: list[_CreditCardRow] = []
    current: _CreditCardRow | None = None

    for raw_line in ocr_text.splitlines():
        line = _clean_line(raw_line)
        if not line:
            continue
        parsed = _parse_transaction_line(line)
        if parsed:
            if current:
                rows.append(current)
            current = parsed
            continue
        if current and _is_continuation_line(line):
            row = current
            current = _CreditCardRow(
                post_month=row.post_month,
                transaction_day=row.transaction_day,
                transaction_month=row.transaction_month,
                description=_clean_description(f"{row.description} {line}"),
                amount=row.amount,
                is_credit=row.is_credit,
                raw_text=f"{row.raw_text}\n{line}",
            )

    if current:
        rows.append(current)
    return rows


def _parse_transaction_line(line: str) -> _CreditCardRow | None:
    if _is_non_transaction_line(line):
        return None
    match = TRANSACTION_LINE_RE.match(line)
    if not match:
        return None

    post_day = _parse_ocr_day(match.group(1))
    post_month = _parse_month(match.group(2))
    transaction_day = _parse_ocr_day(match.group(3))
    transaction_month = _parse_month(match.group(4))
    if post_day is None or post_month is None or transaction_day is None or transaction_month is None:
        return None

    amount = _normalize_amount(match.group("amount"))
    if _amount_to_decimal(amount) is None:
        return None

    description = _clean_description(match.group("body"))
    if not description:
        return None

    return _CreditCardRow(
        post_month=post_month,
        transaction_day=transaction_day,
        transaction_month=transaction_month,
        description=description,
        amount=amount,
        is_credit=bool(match.group("cr")),
        raw_text=line,
    )


def _find_statement_year_month(ocr_text: str) -> tuple[int | None, int | None]:
    for raw_line in ocr_text.splitlines():
        line = _clean_line(raw_line)
        match = STATEMENT_DATE_RE.search(line)
        if not match:
            continue
        month = _parse_month(match.group(2))
        year = _normalize_year(match.group(3))
        if month is not None and year is not None:
            return year, month

    for match in ANY_YEAR_DATE_RE.finditer(ocr_text):
        month = _parse_month(match.group(2))
        year = _normalize_year(match.group(3))
        if month is not None and year is not None:
            return year, month

    return None, None


def _format_transaction_date(
    day: int,
    month: int,
    statement_year: int | None,
    statement_month: int | None,
) -> str | None:
    if statement_year is None:
        return None

    year = statement_year
    if statement_month == 1 and month == 12:
        year -= 1

    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _is_non_transaction_line(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line).strip().upper()
    return any(phrase in normalized for phrase in NON_TRANSACTION_PHRASES)


def _is_continuation_line(line: str) -> bool:
    if _is_non_transaction_line(line):
        return False
    if not re.search(r"[A-Za-z]", line):
        return False
    if re.search(r"\d[\d,]*\.\d{2}\s*(?:CR)?$", line, re.IGNORECASE):
        return False
    if re.match(r"^[0O]?\d{1,2}\s+[0O]?\d{1,2}\b", line, re.IGNORECASE):
        return False
    return True


def _clean_description(description: str) -> str:
    description = re.sub(r"\s+", " ", description).strip()
    return description.strip(" |")


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _parse_ocr_day(value: str) -> int | None:
    normalized = value.replace("O", "0").replace("o", "0")
    if not normalized.isdigit():
        return None
    day = int(normalized)
    if not 1 <= day <= 31:
        return None
    return day


def _parse_month(value: str) -> int | None:
    return MONTHS.get(value[:3].upper())


def _normalize_year(value: str) -> int | None:
    normalized = value.replace("O", "0").replace("o", "0")
    if not normalized.isdigit():
        return None
    if len(normalized) == 2:
        return int(f"20{normalized}")
    if len(normalized) == 4:
        return int(normalized)
    return None


def _normalize_amount(amount: str) -> str:
    amount = amount.strip()
    negative = amount.startswith("(") and amount.endswith(")")
    amount = amount.strip("()")
    if negative and not amount.startswith("-"):
        amount = f"-{amount}"
    return amount


def _amount_to_decimal(amount: str) -> Decimal | None:
    normalized = amount.strip().replace(",", "")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None
