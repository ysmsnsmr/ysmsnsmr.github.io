from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
from typing import Any

from .models import ALLOWED_TREATMENTS, Transaction


class RuleError(ValueError):
    pass


def load_rules(path: str | Path) -> list[dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    data = _load_yaml_rules(text)
    rules = data.get("rules")
    if not isinstance(rules, list):
        raise RuleError("rules.yml must contain a top-level 'rules' list.")

    normalized: list[dict[str, Any]] = []
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
        normalized_rule: dict[str, Any] = {
            "pattern": pattern,
            "category": category,
            "treatment": treatment,
        }
        normalized_rule.update(_normalize_rule_metadata(rule, index))
        normalized.append(normalized_rule)
    audit_errors = audit_rule_errors(normalized)
    if audit_errors:
        raise RuleError("rules.yml audit failed: " + "; ".join(audit_errors))
    return normalized


def categorize_transactions(
    transactions: list[Transaction], rules: list[dict[str, Any]]
) -> list[Transaction]:
    return [categorize_transaction(transaction, rules) for transaction in transactions]


def categorize_transaction(transaction: Transaction, rules: list[dict[str, Any]]) -> Transaction:
    haystack = f"{transaction.description}\n{transaction.raw_text}"
    matched_rule = None
    for rule in rules:
        if matches_rule(rule["pattern"], haystack):
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


def matches_rule(pattern: str, haystack: str) -> bool:
    if re.search(re.escape(pattern), haystack, flags=re.IGNORECASE):
        return True

    # OCR may insert punctuation into an otherwise unchanged merchant name.
    normalized_pattern = normalize_rule_text(pattern)
    normalized_haystack = normalize_rule_text(haystack)
    return _normalized_pattern_matches(normalized_pattern, normalized_haystack)


def normalize_rule_text(value: str) -> str:
    without_punctuation = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", without_punctuation).casefold().strip()


def audit_rule_errors(rules: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    normalized_patterns: dict[str, tuple[int, dict[str, Any]]] = {}

    for index, rule in enumerate(rules, start=1):
        normalized_pattern = normalize_rule_text(rule["pattern"])
        existing = normalized_patterns.get(normalized_pattern)
        if existing:
            existing_index, existing_rule = existing
            errors.append(
                f"Rule {index} pattern '{rule['pattern']}' duplicates Rule {existing_index} "
                f"pattern '{existing_rule['pattern']}' after normalization"
            )
        else:
            normalized_patterns[normalized_pattern] = (index, rule)

    for later_index, later_rule in enumerate(rules):
        later_classification = (later_rule["category"], later_rule["treatment"])
        for earlier_index, earlier_rule in enumerate(rules[:later_index]):
            if normalize_rule_text(earlier_rule["pattern"]) == normalize_rule_text(
                later_rule["pattern"]
            ):
                continue
            earlier_classification = (earlier_rule["category"], earlier_rule["treatment"])
            if (
                earlier_classification != later_classification
                and matches_rule(earlier_rule["pattern"], later_rule["pattern"])
            ):
                errors.append(
                    f"Rule {later_index + 1} pattern '{later_rule['pattern']}' is shadowed by "
                    f"Rule {earlier_index + 1} pattern '{earlier_rule['pattern']}' with a "
                    "different classification"
                )

    return errors


def _normalize_rule_metadata(rule: dict[str, Any], index: int) -> dict[str, Any]:
    metadata: dict[str, Any] = {}

    if "reason" in rule and rule["reason"] is not None:
        reason = rule["reason"]
        if not isinstance(reason, str):
            raise RuleError(f"Rule {index} metadata 'reason' must be a string.")
        metadata["reason"] = reason.strip()

    if "first_confirmed_month" in rule and rule["first_confirmed_month"] is not None:
        first_confirmed_month = str(rule["first_confirmed_month"]).strip()
        if not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", first_confirmed_month):
            raise RuleError(
                f"Rule {index} metadata 'first_confirmed_month' must use YYYY-MM format."
            )
        metadata["first_confirmed_month"] = first_confirmed_month

    if "confirmation_count" in rule and rule["confirmation_count"] is not None:
        confirmation_count = rule["confirmation_count"]
        if isinstance(confirmation_count, bool):
            raise RuleError(
                f"Rule {index} metadata 'confirmation_count' must be a non-negative integer."
            )
        try:
            parsed_count = int(confirmation_count)
        except (TypeError, ValueError):
            raise RuleError(
                f"Rule {index} metadata 'confirmation_count' must be a non-negative integer."
            ) from None
        if parsed_count < 0 or str(confirmation_count).strip() != str(parsed_count):
            raise RuleError(
                f"Rule {index} metadata 'confirmation_count' must be a non-negative integer."
            )
        metadata["confirmation_count"] = parsed_count

    return metadata


def _normalized_pattern_matches(normalized_pattern: str, normalized_haystack: str) -> bool:
    if not normalized_pattern:
        return False
    boundary_pattern = rf"(?<!\w){re.escape(normalized_pattern)}(?!\w)"
    return re.search(boundary_pattern, normalized_haystack) is not None


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
