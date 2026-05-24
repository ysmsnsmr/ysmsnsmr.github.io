from __future__ import annotations

import re


CREDIT_CARD_MARKERS = (
    "CREDIT CARD-I",
    "PAYMENT DUE DATE",
    "CARD NUMBER",
    "CASH BACK SUMMARY",
    "PREVIOUS STATEMENT BALANCE",
    "MINIMUM MONTHLY PAYMENT",
)


def is_credit_card_statement(ocr_text: str) -> bool:
    normalized = re.sub(r"\s+", " ", ocr_text).upper()
    marker_count = sum(1 for marker in CREDIT_CARD_MARKERS if marker in normalized)
    return marker_count >= 3
