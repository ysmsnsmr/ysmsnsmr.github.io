#!/usr/bin/env python3
"""Independent Groq review for structured Japanese news entries."""

import json
import re
import urllib.request
from typing import Any


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_USER_AGENT = "ysmsnsmr-malaysia-news/0.1 (+https://ysmsnsmr.github.io/news/malaysia/)"
MAX_REVIEW_RESPONSE_CHARS = 4000
ENTRY_REVIEW_TIMEOUT_SECONDS = 30
ENTRY_REVIEW_MAX_TOKENS = 500


ENTRY_REVIEW_SYSTEM_PROMPT = """あなたは日本語ニュース入口文の厳格な検品担当です。
原文のtitle、description、許可された短いbody_evidenceと、生成済みentryを比較してください。
検品対象は記事の主体、発言者・帰属、出来事の状態、確定度です。
原文にない事実を追加しないでください。
計画、提案、予報、警報、調査、疑惑、否定を完了・確定した事実に変えないでください。
問題がなければverdictはpass、修正すればentryを正しくできる場合はrevise、主体・帰属・状態・確定度を安全に保てない場合はrejectにしてください。
passまたはreviseでは、検品後の完全なentry objectをreviewed_entryに入れてください。
reviseでは必要な意味修正だけを行い、文章を華美に書き換えないでください。
rejectではreviewed_entryをnullにしてください。
issuesには短い英語または日本語の理由を入れてください。
source_textは入力された原文からそのまま抜き出してください。
出力は次のJSON objectだけにしてください: {"verdict":"pass|revise|reject","issues":[],"reviewed_entry":{"text_ja":"...","subject":{},"attribution":null,"state":{},"certainty":{}}}
"""


def clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def entry_review_payload(item: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": item.get("title"),
        "description": item.get("description"),
        "entry": entry,
    }
    if item.get("body_excerpt_policy") == "use_body":
        excerpt = clean_text(item.get("body_evidence_excerpt"))
        if excerpt:
            payload["body_evidence"] = {
                "excerpt": excerpt,
                "focus": item.get("body_evidence_focus")
                if isinstance(item.get("body_evidence_focus"), list)
                else [],
                "forbidden": item.get("body_evidence_forbidden")
                if isinstance(item.get("body_evidence_forbidden"), list)
                else [],
            }
    return payload


def strip_json_code_fence(content: str) -> str:
    text = content.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return fence_match.group(1).strip() if fence_match else text


def parse_entry_review_content(content: str) -> dict[str, Any]:
    value = json.loads(strip_json_code_fence(content))
    if not isinstance(value, dict):
        raise ValueError("entry review is not object")
    verdict = clean_text(value.get("verdict")).lower()
    if verdict not in {"pass", "revise", "reject"}:
        raise ValueError("invalid entry review verdict")
    raw_issues = value.get("issues")
    if raw_issues is None:
        raw_issues = []
    if not isinstance(raw_issues, list):
        raise ValueError("entry review issues is not list")
    issues = [clean_text(issue) for issue in raw_issues if clean_text(issue)]
    reviewed_entry = value.get("reviewed_entry")
    if verdict in {"pass", "revise"} and not isinstance(reviewed_entry, dict):
        raise ValueError("entry review is missing reviewed_entry")
    if verdict == "reject":
        reviewed_entry = None
    return {
        "verdict": verdict,
        "issues": issues[:8],
        "reviewed_entry": reviewed_entry,
    }


def request_entry_review(
    item: dict[str, Any],
    entry: dict[str, Any],
    api_key: str,
    model: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": ENTRY_REVIEW_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(entry_review_payload(item, entry), ensure_ascii=False),
            },
        ],
        "temperature": 0.0,
        "max_tokens": ENTRY_REVIEW_MAX_TOKENS,
        "stream": False,
    }
    if model.startswith("openai/gpt-oss-"):
        body["include_reasoning"] = False
        body["reasoning_effort"] = "low"
    else:
        body["response_format"] = {"type": "json_object"}

    request = urllib.request.Request(
        GROQ_CHAT_COMPLETIONS_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": GROQ_USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=ENTRY_REVIEW_TIMEOUT_SECONDS) as response:
        response_body = response.read(MAX_REVIEW_RESPONSE_CHARS + 1).decode("utf-8", errors="replace")
    if len(response_body) > MAX_REVIEW_RESPONSE_CHARS:
        raise ValueError("entry review response too long")
    payload = json.loads(response_body)
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("entry review response content is empty")
    if len(content) > MAX_REVIEW_RESPONSE_CHARS:
        raise ValueError("entry review message content too long")
    return parse_entry_review_content(content)
