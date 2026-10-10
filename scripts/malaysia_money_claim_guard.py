"""Check explicit monetary claims against source amounts without exchange rates."""

import re
from decimal import Decimal


_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_SCALE = r"billion|bilion|million|juta|thousand|ribu|bn|b|m|k"
_PREFIXED = re.compile(
    rf"(?<![A-Za-z])(?P<currency>US\$|RM|MYR|USD|JPY|\$|¥|ringgit|yen|dollars?)\s*"
    rf"(?P<number>{_NUMBER})(?:\s*(?P<scale>{_SCALE}))?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_SUFFIXED = re.compile(
    rf"(?<![\d,])(?P<number>{_NUMBER})(?:\s*(?P<scale>{_SCALE}))?\s+"
    r"(?P<currency>ringgit|yen|dollars?)\b",
    re.IGNORECASE,
)
_JAPANESE = re.compile(
    rf"(?<![\d,])(?P<amount>{_NUMBER}(?:\s*(?:千万|百万|十万|兆|億|万|千|百|十))?"
    rf"(?:\s*{_NUMBER}\s*(?:千万|百万|十万|億|万|千|百|十))*)\s*"
    r"(?P<currency>リンギット|米ドル|ドル|円)"
)
_JAPANESE_PIECE = re.compile(rf"({_NUMBER})\s*(千万|百万|十万|[兆億万千百十]?)")
_UNPARSED_AMOUNT = re.compile(
    r"(?:\d[\d,.]*|数[千百万億兆]?|[一二三四五六七八九十百千万億兆]+)"
    r"\s*[千百万億兆]*\s*(?:リンギット|米ドル|ドル|円)"
    r"|(?<![A-Za-z])(?:RM|MYR|USD|JPY|US\$)\s*[一二三四五六七八九十百千万億兆\d]",
    re.IGNORECASE,
)
_MULTIPLIERS = {
    "billion": Decimal(1_000_000_000),
    "bilion": Decimal(1_000_000_000),
    "bn": Decimal(1_000_000_000),
    "b": Decimal(1_000_000_000),
    "million": Decimal(1_000_000),
    "juta": Decimal(1_000_000),
    "m": Decimal(1_000_000),
    "thousand": Decimal(1_000),
    "ribu": Decimal(1_000),
    "k": Decimal(1_000),
    "兆": Decimal(1_000_000_000_000),
    "億": Decimal(100_000_000),
    "万": Decimal(10_000),
    "千": Decimal(1_000),
    "百": Decimal(100),
    "十": Decimal(10),
    "十万": Decimal(100_000),
    "百万": Decimal(1_000_000),
    "千万": Decimal(10_000_000),
    "": Decimal(1),
}


def _currency(value: str) -> str:
    token = value.lower()
    if token in {"rm", "myr", "ringgit", "リンギット"}:
        return "MYR"
    if token in {"us$", "usd", "米ドル"}:
        return "USD"
    if token in {"$", "dollar", "dollars", "ドル"}:
        return "DOLLAR_UNSPECIFIED"
    return "JPY"


def _japanese_value(amount: str) -> Decimal:
    return sum(
        (Decimal(number.replace(",", "")) * _MULTIPLIERS[unit] for number, unit in _JAPANESE_PIECE.findall(amount)),
        Decimal(0),
    )


def monetary_claims(text: str) -> set[tuple[str, Decimal]]:
    claims: set[tuple[str, Decimal]] = set()
    for pattern in (_PREFIXED, _SUFFIXED):
        for match in pattern.finditer(text):
            number = Decimal(match.group("number").replace(",", ""))
            scale = (match.group("scale") or "").lower()
            claims.add((_currency(match.group("currency")), number * _MULTIPLIERS[scale]))
    for match in _JAPANESE.finditer(text):
        claims.add((_currency(match.group("currency")), _japanese_value(match.group("amount"))))
    return claims


def source_money_literals(text: str) -> list[str]:
    """Preserve source spelling and order for the model's money references."""
    matches = [
        match for pattern in (_PREFIXED, _SUFFIXED, _JAPANESE)
        for match in pattern.finditer(text)
    ]
    return list(dict.fromkeys(match.group(0).strip() for match in sorted(matches, key=lambda match: match.start())))


def unsupported_money_claim_reason(source_text: str, rendered_text: str) -> str:
    source_claims = monetary_claims(source_text)
    rendered_claims = monetary_claims(rendered_text)
    remaining = rendered_text
    for pattern in (_PREFIXED, _SUFFIXED, _JAPANESE):
        remaining = pattern.sub(" ", remaining)
    if _UNPARSED_AMOUNT.search(remaining):
        return "monetary amount could not be verified"
    if (re.search(r"(?<=[0-9０-９万億兆千百十])円", rendered_text) or any(
        currency == "JPY" for currency, _ in rendered_claims
    )) and not any(
        currency == "JPY" for currency, _ in source_claims
    ):
        return "unsupported yen conversion"
    if rendered_claims - source_claims:
        return "monetary amount or currency not supported by source"
    return ""
