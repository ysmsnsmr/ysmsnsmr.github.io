from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
from typing import Any

from .models import ALLOWED_TREATMENTS, Transaction


class RuleError(ValueError):
    pass


def load_rules(path: str | Path) -> list[dict[str, str]]:
    text = Path(path).read_text(encoding="utf-8")
    data = _load_yaml_rules(text)
    rules = data.get("rules")
    if not isinstance(rules, list):
        raise RuleError("rules.yml must contain a top-level 'rules' list.")

    normalized: list[dict[str, str]] = []
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            raise RuleError(f"Rule {index} must be a mapping.")
        pattern = str(rule.get("pattern", "")).strip()
        category = str(rule.get("category", "")).strip()
        treatment = str(rule.get("treatment", "")).strip()
        if not pattern or not category or not treatment:
            raise RuleError(f"Rule {index} must include pattern, category, and treatment.")
        if treatment not in ALLOWED_TREATMENTS:
            allowed = ", ".join(sorted(ALLOWED_TREATMENTS))
            raise RuleError(f"Rule {index} has invalid treatment '{treatment}'. Allowed: {allowed}.")
        normalized.append(
            {
                "pattern": pattern,
                "category": category,
                "treatment": treatment,
            }
        )
    return normalized


def categorize_transactions(
    transactions: list[Transaction], rules: list[dict[str, str]]
) -> list[Transaction]:
    return [categorize_transaction(transaction, rules) for transaction in transactions]


def categorize_transaction(transaction: Transaction, rules: list[dict[str, str]]) -> Transaction:
    haystack = f"{transaction.description}\n{transaction.raw_text}"
    matched_rule = None
    for rule in rules:
        if re.search(re.escape(rule["pattern"]), haystack, flags=re.IGNORECASE):
            matched_rule = rule
            break

    if matched_rule is None:
        return replace(
            transaction,
            category="Other",
            treatment="unknown",
            status="review",
        )

    updated = replace(
        transaction,
        category=matched_rule["category"],
        treatment=matched_rule["treatment"],
    )
    status = "review" if updated.review_reasons else "auto"
    return replace(updated, status=status)


def _load_yaml_rules(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return _load_simple_rules_yaml(text)
    loaded = yaml.safe_load(text) or {}
    if not isinstance(loaded, dict):
        raise RuleError("rules.yml must contain a mapping.")
    return loaded


def _load_simple_rules_yaml(text: str) -> dict[str, Any]:
    rules: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line == "rules:":
            continue
        if line.startswith("- "):
            if current:
                rules.append(current)
            current = {}
            line = line[2:].strip()
            if line:
                key, value = _parse_key_value(line)
                current[key] = value
            continue
        if current is None:
            raise RuleError("Only a top-level rules list is supported without PyYAML.")
        key, value = _parse_key_value(line)
        current[key] = value

    if current:
        rules.append(current)
    return {"rules": rules}


def _parse_key_value(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise RuleError(f"Invalid rules.yml line: {line}")
    key, value = line.split(":", 1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key.strip(), value
