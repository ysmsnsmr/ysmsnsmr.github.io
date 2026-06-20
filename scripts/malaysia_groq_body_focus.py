#!/usr/bin/env python3
from typing import Any

from malaysia_groq_common import clean_text, has_any_text, looks_generic


BODY_FOCUS_LIFE_IMPACT_CUES = {
    "procedure_or_public_service": [
        "申請",
        "期限",
        "対象",
        "窓口",
        "手続き",
        "制度",
        "利用",
        "確認",
    ],
    "cost_or_subsidy": [
        "家計",
        "価格",
        "補助",
        "対象",
        "支払い",
        "負担",
        "生活費",
        "費用",
    ],
    "transport_or_infra": [
        "運行",
        "道路",
        "通勤",
        "移動",
        "利用者",
        "交通",
        "路線",
        "駅",
    ],
    "consumer_or_payment": [
        "決済",
        "アプリ",
        "利用",
        "手数料",
        "支払い",
        "カード",
        "サービス",
    ],
    "health_or_education": [
        "受診",
        "医療",
        "医療費",
        "治療費",
        "補助",
        "対象者",
        "学校",
        "対象",
        "学生",
        "教育",
        "健康",
        "費用",
        "負担",
        "病院",
        "クリニック",
    ],
    "financial_service_access": [
        "銀行",
        "金融",
        "窓口",
        "顧客",
        "口座",
        "サービス",
        "利用",
    ],
}


def body_evidence_focus_values(item: dict[str, Any]) -> list[str]:
    if item.get("body_excerpt_policy") != "use_body":
        return []
    focus = item.get("body_evidence_focus")
    if not isinstance(focus, list):
        return []
    return [clean_text(value) for value in focus if clean_text(value)]


def life_impact_matches_body_focus(item: dict[str, Any], life_impact: str) -> bool:
    focus_values = body_evidence_focus_values(item)
    if not focus_values:
        return True
    text = clean_text(life_impact)
    if not text:
        return False
    if looks_generic(text):
        return False
    if "health_or_education" in focus_values and has_any_text(text, ["背景情報", "確認しておく価値"]):
        return False
    allowed_cues: list[str] = []
    for focus in focus_values:
        allowed_cues.extend(BODY_FOCUS_LIFE_IMPACT_CUES.get(focus, []))
    if not allowed_cues:
        return True
    return any(cue in text for cue in allowed_cues)
