"""Common entry point for bank/debit and credit-card statement parsers."""

from __future__ import annotations

from typing import Literal

from .credit_card_parser import parse_transactions as parse_credit_card_transactions
from .models import Transaction
from .parser import parse_transactions as parse_bank_transactions
from .statement_type import is_credit_card_statement


StatementType = Literal["bank_debit", "credit_card"]


def parse_statement(ocr_text: str) -> tuple[StatementType, list[Transaction]]:
    """Detect the statement format and delegate to its existing parser.

    The format-specific parsers remain independent and continue to return
    ``list[Transaction]``. This function only provides their shared boundary.
    """
    if is_credit_card_statement(ocr_text):
        return "credit_card", parse_credit_card_transactions(ocr_text)
    return "bank_debit", parse_bank_transactions(ocr_text)
