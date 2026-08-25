#!/usr/bin/env python3
"""Render selected Malaysia news through the Editorial Entry v2 contract.

The production path has one display object. Groq may replace the code-owned
RSS fallback entry only after a strict JSON and hard-safety check; every other
outcome keeps the selected URL renderable without reusing legacy RSS prose.
"""

import argparse
import copy
import json
import os
import re
import sys
import time
import urllib.error
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from malaysia_groq_common import clean_text, has_any_text, item_source_text
from malaysia_groq_force_all_policy import force_all_request_cap
from malaysia_groq_model_profiles import (
    COMPARISON_CONTRACTS,
    COMPARISON_PROMPT_LAYOUTS,
    DEFAULT_COMPARISON_MAX_TOKENS,
    ModelProfile,
    load_model_profile_registry,
    profile_for_model_id,
    production_model_profile,
)
from malaysia_groq_output_contract import (
    EDITORIAL_ENTRY_V2_SCHEMA,
    editorial_entry_forbidden_patterns,
    editorial_entry_schema_error,
    headline_is_valid,
)
from malaysia_groq_render_decision import (
    apply_render_decisions,
    annotate_decision_records,
    build_render_decisions,
    provenance_observation,
)
from malaysia_groq_transport import error_diagnostic, request_chat_completion
import render_malaysia_news_from_json as fallback_renderer


DEFAULT_MODEL = production_model_profile("", load_model_profile_registry()).model_id
MAX_RESPONSE_CHARS = 4000
TIMEOUT_SECONDS = 30
MAX_429_RETRY_AFTER_SECONDS = 5

SYSTEM_PROMPT = """あなたはマレーシア在住者向けニュースダッシュボードの日本語編集者です。
入力はRSSのtitle、description、既存のRSS entry、必要に応じてbody_evidenceだけです。
body_evidenceがない場合はRSSの情報だけを使ってください。入力にない事実を追加せず、カテゴリ、出典、URL、日付は変更しないでください。
英語またはマレー語の文を、自然で短い日本語に整えてください。dateline、wire credit、広告、関連記事、body_evidence.forbiddenの要素は出力しません。
返答はeditorial_entryだけを持つJSON objectです。headline_jaは一覧に載せる短見出しです。全角文字は1、半角英数字・記号は0.5として15.5文字幅以内にし、末尾に「…」を付けず、記事の主体と出来事または注意点が分かる自然な日本語にしてください。入力にない固有名詞・数値・断定は加えないでください。
entry_jaは、読者が出典リンクを開くか判断できる日本語の概要です。主体、発言者・帰属、計画・提案・予報・調査・疑惑・否定などの確定度を、自然文の中で落とさないでください。
発言記事では発言者または当局を自然に残してください。計画・提案・予報・警報・調査・疑惑・否定を、完了・確定した事実として書き換えないでください。
supporting_points_jaは0〜2件の補足事実です。生活影響や次アクションを独立項目として作らず、入力に明確な根拠がある場合だけ概要または補足に自然に含めてください。
RSSにない数値、対象者、死亡、事故、被害、収入減、因果関係を足さないでください。“lost students”, “losing students” は死亡を意味すると明確でない限り、利用者・生徒の減少として訳してください。
出力はJSONのみです。"""

EDITORIAL_ENTRY_V2_CONTRACT_INSTRUCTION = """返答は次の形のJSON objectだけにしてください。追加のkey、説明文、Markdownは出力しません。
{"editorial_entry":{"headline_ja":"string","entry_ja":"string","supporting_points_ja":["string"]}}"""

# Kept as an import-compatible alias for the comparison runner while profiles
# move to the sole v2 contract.
USER_MESSAGE_JSON_CONTRACT = EDITORIAL_ENTRY_V2_CONTRACT_INSTRUCTION


@dataclass
class GroqEditorialEntryResult:
    editorial_entry: dict[str, Any]
    transport_diagnostic: dict[str, Any]


class GroqEditorialEntryRejected(ValueError):
    """Expose transport diagnostics when a returned entry fails hard safety."""

    def __init__(self, reason: str, transport_diagnostic: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.transport_diagnostic = copy.deepcopy(transport_diagnostic) if isinstance(transport_diagnostic, dict) else None


# Legacy public name retained for scripts that catch the old exception.
GroqSummaryRejected = GroqEditorialEntryRejected


def normalize_editorial_entry(value: Any) -> dict[str, Any]:
    entry = value if isinstance(value, dict) else {}
    points = entry.get("supporting_points_ja")
    return {
        "headline_ja": clean_text(entry.get("headline_ja")),
        "entry_ja": clean_text(entry.get("entry_ja")),
        "supporting_points_ja": [
            clean_text(point) for point in points if clean_text(point)
        ][:2]
        if isinstance(points, list)
        else [],
    }


def editorial_entry_text(entry: dict[str, Any]) -> str:
    return " ".join(
        [clean_text(entry.get("headline_ja")), clean_text(entry.get("entry_ja")), *entry.get("supporting_points_ja", [])]
    ).strip()


def groq_payload_for_item(item: dict[str, Any]) -> dict[str, Any]:
    """The model sees article facts plus the RSS fallback, never legacy fields."""
    payload: dict[str, Any] = {
        "category": item.get("category"),
        "source": item.get("source"),
        "published_date": item.get("published_date"),
        "title": item.get("title"),
        "description": item.get("description"),
        "rss_editorial_entry": fallback_renderer.normalize_editorial_entry(item),
        "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
        "flags": item.get("flags") if isinstance(item.get("flags"), dict) else {},
    }
    if item.get("body_excerpt_policy") == "use_body":
        excerpt = clean_text(item.get("body_evidence_excerpt"))
        if excerpt:
            payload["body_evidence"] = {
                "excerpt": excerpt,
                "forbidden": item.get("body_evidence_forbidden")
                if isinstance(item.get("body_evidence_forbidden"), list)
                else [],
            }
    return payload


def summary_request_messages(
    item: dict[str, Any],
    prompt_layout: str = "production",
    summary_contract: str = "editorial_entry_v2",
) -> list[dict[str, str]]:
    if prompt_layout not in COMPARISON_PROMPT_LAYOUTS:
        raise ValueError(f"unsupported summary prompt layout: {prompt_layout}")
    if summary_contract not in COMPARISON_CONTRACTS:
        raise ValueError(f"unsupported summary contract: {summary_contract}")
    article_json = json.dumps(groq_payload_for_item(item), ensure_ascii=False)
    if prompt_layout == "production":
        return [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{EDITORIAL_ENTRY_V2_CONTRACT_INSTRUCTION}"},
            {"role": "user", "content": article_json},
        ]
    content = (
        f"{SYSTEM_PROMPT}\n\n{EDITORIAL_ENTRY_V2_CONTRACT_INSTRUCTION}\n\n"
        f"入力記事JSON:\n{article_json}"
    )
    return [{"role": "user", "content": content}]


def is_enriched_json(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if isinstance(data.get("body_enrichment"), dict):
        return True
    items = data.get("items")
    return isinstance(items, list) and any(
        isinstance(item, dict) and "body_excerpt_policy" in item for item in items
    )


def resolve_json_input(path: str) -> Path:
    input_path = Path(path)
    if not input_path.exists():
        return input_path
    try:
        data = fallback_renderer.load_json(str(input_path))
    except Exception:
        return input_path
    if is_enriched_json(data):
        return input_path
    for candidate in (
        input_path.with_name(f"{input_path.stem}_enriched{input_path.suffix}"),
        input_path.with_name("selected_items_enriched.json"),
    ):
        try:
            if candidate.exists() and is_enriched_json(fallback_renderer.load_json(str(candidate))):
                return candidate
        except Exception:
            continue
    return input_path


def debug_groq_payload(index: int, item: dict[str, Any], reason: str = "") -> None:
    suffix = f" reason={reason}" if reason else ""
    print(
        f"groq-debug: item={index + 1} title={clean_text(item.get('title'))[:80]!r}{suffix}",
        file=sys.stderr,
    )


def rendered_has_japanese_unit_for_number(rendered_text: str, number: str, units: list[str]) -> bool:
    normalized_number = re.escape(number.rstrip("."))
    unit_pattern = "|".join(re.escape(unit) for unit in units)
    return re.search(rf"(?<![0-9]){normalized_number}\s*(?:{unit_pattern})", rendered_text) is not None


def reject_numeric_unit_reason(source_text: str, rendered_text: str) -> str:
    for pattern in (
        r"\bRM\s*([0-9]+(?:\.[0-9]+)?)\s*(?:b|bn|billion)\b",
        r"\b([0-9]+(?:\.[0-9]+)?)\s*billion\b",
    ):
        for match in re.finditer(pattern, source_text, flags=re.IGNORECASE):
            if rendered_has_japanese_unit_for_number(rendered_text, match.group(1), ["億", "億リンギット", "万人"]):
                return f"unsafe numeric unit conversion: {match.group(0)}"
    for match in re.finditer(r"\b([0-9]+(?:\.[0-9]+)?)\s*million\b", source_text, flags=re.IGNORECASE):
        if rendered_has_japanese_unit_for_number(rendered_text, match.group(1), ["万人", "万"]):
            return f"unsafe numeric unit conversion: {match.group(0)}"
    return ""


def reject_currency_token_reason(source_text: str, rendered_text: str) -> str:
    if not re.search(r"\bRM\s*1\b", source_text, flags=re.IGNORECASE):
        return ""
    if re.search(
        r"1月\s*7(?:日)?\s*(?:マレーシア)?\s*(?:Ringgit|リンギット)|"
        r"1月\s*(?:マレーシア)?\s*(?:Ringgit|リンギット)",
        rendered_text,
        flags=re.IGNORECASE,
    ):
        return "unsafe RM1 date/currency conversion"
    return ""


def validate_editorial_entry_against_source(item: dict[str, Any], entry: dict[str, Any]) -> None:
    source_text = item_source_text(item)
    rendered_text = editorial_entry_text(entry)
    if not rendered_text:
        raise ValueError("missing entry_ja")
    if "学生を失った" in rendered_text and not has_any_text(source_text, ["death", "dead", "died", "killed", "fatal", "meninggal", "maut"]):
        raise ValueError("unsafe losing students wording")
    if any(
        marker in rendered_text
        for marker in (
            "KUALA LUMPUR, May ",
            "PUTRAJAYA, May ",
            "IPOH, May ",
            "ALOR SETAR, May ",
            "GEORGE TOWN, May ",
            "JOHOR BARU, May ",
            "KOTA KINABALU, May ",
            "KUCHING, May ",
            "— The ",
            "— A ",
            "— An ",
        )
    ):
        raise ValueError("english lead leakage")
    if editorial_entry_forbidden_patterns(rendered_text):
        raise ValueError("forbidden display leakage")
    for reason in (
        reject_numeric_unit_reason(source_text, rendered_text),
        reject_currency_token_reason(source_text, rendered_text),
    ):
        if reason:
            raise ValueError(reason)
    guarded_claims = {
        "death": (["死亡", "亡くな", "死者"], ["death", "dead", "died", "killed", "fatal", "meninggal", "maut"]),
        "accident": (["事故"], ["accident", "crash", "collision", "kemalangan"]),
        "damage": (["被害"], ["damage", "damaged", "losses", "kerosakan", "被害"]),
        "income_loss": (["収入減", "収入が減", "所得減", "売上減"], ["income", "revenue", "earnings", "salary", "wage", "fare", "lost students", "losing students"]),
    }
    for name, (phrases, evidence) in guarded_claims.items():
        if any(phrase in rendered_text for phrase in phrases) and not has_any_text(source_text, evidence):
            raise ValueError(f"unsupported {name} claim")


def validate_groq_editorial_entry(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("editorial entry response is not object")
    entry = normalize_editorial_entry(value.get("editorial_entry"))
    if not entry["headline_ja"]:
        raise ValueError("missing headline_ja")
    if not headline_is_valid(entry["headline_ja"]):
        raise ValueError("headline_ja exceeds 15.5 display width")
    if not entry["entry_ja"]:
        raise ValueError("missing entry_ja")
    raw = value.get("editorial_entry")
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("headline_ja"), str)
        or not isinstance(raw.get("supporting_points_ja"), list)
    ):
        raise ValueError("editorial_entry fields are invalid")
    return entry


def retry_after_seconds(error: urllib.error.HTTPError, max_seconds: int) -> int | None:
    raw = error.headers.get("Retry-After") if error.headers else None
    if not raw or not raw.strip().isdigit():
        return None
    seconds = int(raw.strip())
    return seconds if 0 <= seconds <= max_seconds else None


def request_groq_summary(
    item: dict[str, Any],
    api_key: str,
    model: str,
    debug: bool = False,
    index: int = 0,
    model_profile: ModelProfile | None = None,
    summary_prompt_layout: str = "production",
    summary_max_tokens: int = DEFAULT_COMPARISON_MAX_TOKENS,
    summary_contract: str = "editorial_entry_v2",
) -> GroqEditorialEntryResult:
    if not isinstance(summary_max_tokens, int) or isinstance(summary_max_tokens, bool) or summary_max_tokens < 1:
        raise ValueError("summary max_tokens must be a positive integer")
    if summary_contract != "editorial_entry_v2":
        raise ValueError(f"unsupported summary contract: {summary_contract}")
    completion = request_chat_completion(
        profile=model_profile or profile_for_model_id(model),
        messages=summary_request_messages(item, summary_prompt_layout, summary_contract),
        temperature=0.2,
        max_tokens=summary_max_tokens,
        timeout_seconds=TIMEOUT_SECONDS,
        max_response_chars=MAX_RESPONSE_CHARS,
        json_schema_name="malaysia_news_editorial_entry_v2",
        json_schema=EDITORIAL_ENTRY_V2_SCHEMA,
        schema_error=editorial_entry_schema_error,
        api_key=api_key,
    )
    try:
        entry = validate_groq_editorial_entry(completion.parsed)
        validate_editorial_entry_against_source(item, entry)
    except ValueError as error:
        raise GroqEditorialEntryRejected(str(error) or "validation failed", completion.diagnostic) from error
    if debug:
        debug_groq_payload(index, item)
    return GroqEditorialEntryResult(entry, completion.diagnostic)


def request_groq_summary_with_retry(
    item: dict[str, Any],
    api_key: str,
    model: str,
    debug: bool = False,
    index: int = 0,
    model_profile: ModelProfile | None = None,
    max_retry_after_seconds: int = MAX_429_RETRY_AFTER_SECONDS,
    summary_prompt_layout: str = "production",
    summary_max_tokens: int = DEFAULT_COMPARISON_MAX_TOKENS,
    summary_contract: str = "editorial_entry_v2",
) -> GroqEditorialEntryResult:
    profile = model_profile or profile_for_model_id(model)
    try:
        return request_groq_summary(
            item, api_key, model, debug, index, profile,
            summary_prompt_layout, summary_max_tokens, summary_contract,
        )
    except urllib.error.HTTPError as error:
        retry_after = retry_after_seconds(error, max_retry_after_seconds)
        if error.code != 429 or retry_after is None:
            raise
        first = error_diagnostic(error)
        time.sleep(retry_after)
        result = request_groq_summary(
            item, api_key, model, debug, index, profile,
            summary_prompt_layout, summary_max_tokens, summary_contract,
        )
        result.transport_diagnostic["attempt_count"] = 2
        result.transport_diagnostic["attempts"] = [first, copy.deepcopy(result.transport_diagnostic)]
        return result


def safe_log(message: str) -> None:
    print(message, file=sys.stderr)


def build_decision_record(index: int, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": index + 1,
        "link": clean_text(item.get("link")),
        "source": clean_text(item.get("source")),
        "category": clean_text(item.get("category")),
        "title": clean_text(item.get("title")),
        "decision": "pending",
        "reason": "",
        "requested": False,
        "accepted": False,
        "render_source_kind": "not_evaluated",
        "groq_call": None,
        "hard_safety_rejection_reason": "",
    }


def decision_record_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "records": len(records),
        "requested": sum(record.get("requested") is True for record in records),
        "accepted": sum(record.get("accepted") is True for record in records),
        "fallback": sum(record.get("decision") == "fallback" for record in records),
        "skipped": sum(record.get("decision") == "skipped" for record in records),
    }


def editorial_entry_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "selected_count": len(records),
        "groq_accepted_count": sum(record.get("render_source_kind") == "groq_accepted" for record in records),
        "rss_fallback_count": sum(record.get("render_source_kind") == "rss_fallback" for record in records),
        "rss_fallback_source_link_only_count": sum(
            record.get("rss_fallback_entry_kind") == "source_link_only" for record in records
        ),
        "request_cap_skipped_count": sum(clean_text(record.get("reason")) == "request_cap" for record in records),
    }


def transport_observation(records: list[dict[str, Any]]) -> dict[str, Any]:
    transport = Counter()
    contracts = Counter()
    hard_safety = Counter()
    for record in records:
        call = record.get("groq_call")
        if isinstance(call, dict):
            transport[clean_text(call.get("transport_status")) or "not_recorded"] += 1
            contracts[clean_text(call.get("json_contract_status")) or "not_evaluated"] += 1
        reason = clean_text(record.get("hard_safety_rejection_reason"))
        if reason:
            hard_safety[reason] += 1
    return {
        "transport_status_counts": dict(sorted(transport.items())),
        "json_contract_status_counts": dict(sorted(contracts.items())),
        "hard_safety_rejection_reason_counts": dict(sorted(hard_safety.items())),
    }


def build_improved_items_payload(
    accepted_records: list[dict[str, Any]],
    model: str,
    stats: dict[str, int],
    now: datetime,
    decision_records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "malaysia-groq-improved-items/v2",
        "generated_at": now.astimezone().isoformat(timespec="seconds"),
        "model": model,
        "counts": {
            "requested": stats["requested"],
            "accepted": stats["accepted"],
            "fallback": stats["fallback"],
        },
        "items": accepted_records,
        "diagnostics": {
            "decision_counts": decision_record_counts(decision_records),
            "editorial_entry_counts": editorial_entry_counts(decision_records),
            "editorial_entry_provenance": provenance_observation(decision_records),
            **transport_observation(decision_records),
            "decision_records": decision_records,
        },
    }


def write_json(path: str, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rate_reset_wait_seconds(diagnostic: Any) -> float | None:
    if not isinstance(diagnostic, dict):
        return None
    rate_limit = diagnostic.get("rate_limit")
    raw = clean_text(rate_limit.get("reset_tokens")) if isinstance(rate_limit, dict) else ""
    match = re.fullmatch(r"(?:(\d+)m)?(\d+(?:\.\d+)?)s", raw)
    if not match:
        return None
    return int(match.group(1) or "0") * 60 + float(match.group(2))


def load_request_link_allowlist(path: str | None) -> set[str] | None:
    if not path:
        return None
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    values = raw.get("links") if isinstance(raw, dict) else raw
    if not isinstance(values, list):
        raise ValueError("request link allowlist must contain a links array")
    links = {clean_text(value) for value in values if clean_text(value)}
    if not links:
        raise ValueError("request link allowlist must not be empty")
    return links


def render_with_groq(
    data: dict[str, Any],
    api_key: str,
    model: str,
    force_all: bool = False,
    debug: bool = False,
    request_link_allowlist: set[str] | None = None,
    rate_reset_wait_max_seconds: int = 0,
    max_retry_after_seconds: int = MAX_429_RETRY_AFTER_SECONDS,
    summary_prompt_layout: str = "production",
    summary_max_tokens: int = DEFAULT_COMPARISON_MAX_TOKENS,
    summary_contract: str = "editorial_entry_v2",
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
    """Call the first cap-selected items in source order; force_all is ignored."""
    rendered = copy.deepcopy(data)
    items = rendered.get("items")
    if not isinstance(items, list):
        return rendered, [], {"requested": 0, "accepted": 0, "fallback": 0}, []
    accepted_records: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    requested = accepted = fallback = 0
    rate_budget_deferred = False
    request_cap = force_all_request_cap()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        record = build_decision_record(index, item)
        records.append(record)
        link = clean_text(item.get("link"))
        if request_link_allowlist is not None and link not in request_link_allowlist:
            record.update(decision="skipped", reason="comparison_cohort_excluded")
            continue
        if not api_key:
            record.update(decision="skipped", reason="missing_groq_api_key")
            continue
        if rate_budget_deferred:
            record.update(decision="skipped", reason="rate_budget_deferred")
            continue
        if requested >= request_cap:
            record.update(decision="skipped", reason="request_cap")
            continue
        requested += 1
        record.update(decision="requested", requested=True)
        try:
            original_entry = fallback_renderer.normalize_editorial_entry(item)
            result = request_groq_summary_with_retry(
                item, api_key, model, debug, index,
                max_retry_after_seconds=max_retry_after_seconds,
                summary_prompt_layout=summary_prompt_layout,
                summary_max_tokens=summary_max_tokens,
                summary_contract=summary_contract,
            )
            item["editorial_entry"] = result.editorial_entry
            record.update(
                decision="accepted",
                accepted=True,
                groq_call=result.transport_diagnostic,
            )
            accepted_records.append(
                {
                    "index": index + 1,
                    "category": item.get("category", ""),
                    "source": item.get("source", ""),
                    "published_date": item.get("published_date", ""),
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "original_editorial_entry": original_entry,
                    "improved_editorial_entry": copy.deepcopy(result.editorial_entry),
                }
            )
            accepted += 1
        except urllib.error.HTTPError as error:
            fallback += 1
            record.update(
                decision="fallback",
                reason=f"HTTP {error.code}",
                groq_call=error_diagnostic(error),
            )
        except GroqEditorialEntryRejected as error:
            fallback += 1
            reason = str(error) or "validation failed"
            record.update(
                decision="fallback",
                reason=f"ValueError: {reason}",
                hard_safety_rejection_reason=reason,
                groq_call=error.transport_diagnostic or error_diagnostic(error),
            )
            if debug:
                debug_groq_payload(index, item, reason)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as error:
            fallback += 1
            record.update(
                decision="fallback",
                reason=error.__class__.__name__,
                groq_call=error_diagnostic(error),
            )
        wait = rate_reset_wait_seconds(record.get("groq_call"))
        if rate_reset_wait_max_seconds > 0 and wait is not None:
            if wait > rate_reset_wait_max_seconds:
                rate_budget_deferred = True
            elif wait > 0:
                time.sleep(wait)
    stats = {"requested": requested, "accepted": accepted, "fallback": fallback}
    records.sort(key=lambda record: record["index"])
    accepted_records.sort(key=lambda record: record["index"])
    return rendered, accepted_records, stats, records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--model", help=f"Defaults to GROQ_MODEL or {DEFAULT_MODEL}.")
    parser.add_argument("--force-all", action="store_true", help="Accepted for compatibility and ignored by Editorial Entry v2.")
    parser.add_argument("--debug-groq", action="store_true")
    parser.add_argument("--summary-prompt-layout", choices=sorted(COMPARISON_PROMPT_LAYOUTS), default="production")
    parser.add_argument("--summary-max-tokens", type=int, default=DEFAULT_COMPARISON_MAX_TOKENS)
    parser.add_argument("--summary-contract", choices=sorted(COMPARISON_CONTRACTS), default="editorial_entry_v2")
    parser.add_argument("--request-link-allowlist")
    parser.add_argument("--rate-reset-wait-max-seconds", type=int, default=0)
    parser.add_argument("--max-429-retry-after-seconds", type=int, default=MAX_429_RETRY_AFTER_SECONDS)
    parser.add_argument("--improved-items-output")
    parser.add_argument("--json-render-output")
    args = parser.parse_args()
    if args.summary_max_tokens < 1:
        parser.error("--summary-max-tokens must be positive")

    data = fallback_renderer.load_json(str(resolve_json_input(args.json_input)))
    model = args.model or os.environ.get("GROQ_MODEL") or DEFAULT_MODEL
    rendered, accepted_records, stats, records = render_with_groq(
        data,
        os.environ.get("GROQ_API_KEY", ""),
        model,
        args.force_all,
        args.debug_groq,
        request_link_allowlist=load_request_link_allowlist(args.request_link_allowlist),
        rate_reset_wait_max_seconds=max(args.rate_reset_wait_max_seconds, 0),
        max_retry_after_seconds=max(args.max_429_retry_after_seconds, 0),
        summary_prompt_layout=args.summary_prompt_layout,
        summary_max_tokens=args.summary_max_tokens,
        summary_contract=args.summary_contract,
    )
    source_items = rendered.get("items")
    decisions = build_render_decisions(source_items if isinstance(source_items, list) else [], records)
    final_data = apply_render_decisions(rendered, decisions)
    annotate_decision_records(data, final_data, records, decisions)
    if args.improved_items_output:
        write_json(
            args.improved_items_output,
            build_improved_items_payload(accepted_records, model, stats, datetime.now(), records),
        )
    markdown = fallback_renderer.render_editorial_entries(final_data)
    for output in (args.output, args.json_render_output):
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(markdown + "\n", encoding="utf-8")
    if not args.output:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
