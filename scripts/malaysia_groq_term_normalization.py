#!/usr/bin/env python3
import re
from typing import Any

from malaysia_groq_common import collect_item_text


def normalize_malaysia_terms_in_text(text: str, item: dict[str, Any]) -> str:
    """Normalize recurring Malaysia-government terms after Groq generation."""
    if not text:
        return text

    source_text = collect_item_text(item)
    source_lower = source_text.lower()
    has_ecoss_evidence = (
        "ecoss" in source_lower
        or "cooking oil price stabilisation scheme" in source_lower
        or "cooking oil price stabilization scheme" in source_lower
    )
    has_kita_selangor_voucher_evidence = "kita selangor" in source_lower and (
        "voucher" in source_lower or "vouchers" in source_lower or "baucar" in source_lower
    )

    replacements = {
        "国内取引・生活費省": "国内貿易・生活費省",
        "国内取引省": "国内貿易省",
        "車両カード": "フリートカード",
    }

    if "kpdn" in source_text or "domestic trade" in source_text:
        replacements.update(
            {
                "商務省": "国内貿易・生活費省",
                "ケダ州商務省": "ケダ州国内貿易・生活費省",
            }
        )

    if has_ecoss_evidence:
        ecoss_label = "eCOSS（食用油価格安定化制度）"
        replacements.update(
            {
                "食用石油価格格安定化制度(eCOSS)": ecoss_label,
                "食用石油価格格安定化制度（eCOSS）": ecoss_label,
                "食用油価格格安定化制度(eCOSS)": ecoss_label,
                "食用油価格格安定化制度（eCOSS）": ecoss_label,
                "食用石油価格安定化制度(eCOSS)": ecoss_label,
                "食用石油価格安定化制度（eCOSS）": ecoss_label,
                "食用油価格安定化制度(eCOSS)": ecoss_label,
                "食用油価格安定化制度（eCOSS）": ecoss_label,
                "食用石油価格格安定化制度": ecoss_label,
                "食用油価格格安定化制度": ecoss_label,
                "食用石油価格安定化制度": ecoss_label,
                "食用油価格安定化制度": ecoss_label,
                "食用石油価格安定制度": ecoss_label,
                "食用油価格安定制度": ecoss_label,
                "eCOSS制度": ecoss_label,
                "eCOSS 制度": ecoss_label,
            }
        )

    if has_kita_selangor_voucher_evidence:
        replacements.update(
            {
                "Kita Selangor voucer": "Kita Selangor voucher",
                "Kita Selangor Voucer": "Kita Selangor voucher",
                "Kita Selangor バウチャー": "Kita Selangor voucher",
                "Kita Selangor バウチャ": "Kita Selangor voucher",
                "キタ・セランゴール・バウチャー": "Kita Selangor voucher",
                "キタセランゴール・バウチャー": "Kita Selangor voucher",
                "キタセランゴールバウチャー": "Kita Selangor voucher",
            }
        )

    for old, new in replacements.items():
        text = text.replace(old, new)
    if has_ecoss_evidence:
        ecoss_label = "eCOSS（食用油価格安定化制度）"
        text = re.sub(
            r"食用(?:石)?(?:石油|油)価格(?:格)?(?:格安|安定)定?化?制度[（(]eCOSS[）)]",
            ecoss_label,
            text,
        )
        text = re.sub(
            r"食用(?:石)?(?:石油|油)価格(?:格)?(?:格安|安定)定?化?制度",
            ecoss_label,
            text,
        )
        nested_ecoss_label = f"eCOSS（{ecoss_label}）"
        while nested_ecoss_label in text:
            text = text.replace(nested_ecoss_label, ecoss_label)
    return text


def normalize_malaysia_terms(summary: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    """Normalize terms in a Groq summary while preserving the summary schema."""
    normalized = dict(summary)
    for key in ("conclusion", "life_impact", "next_action"):
        if isinstance(normalized.get(key), str):
            normalized[key] = normalize_malaysia_terms_in_text(normalized[key], item)
    if isinstance(normalized.get("what_happened"), list):
        normalized["what_happened"] = [
            normalize_malaysia_terms_in_text(str(line), item)
            for line in normalized["what_happened"]
            if line
        ]
    return normalized
