"""OpenAI Chat Completions transport for Malaysia News editorial output."""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from malaysia_groq_model_profiles import ModelProfile


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_USER_AGENT = "ysmsnsmr-malaysia-news/0.1 (+https://ysmsnsmr.github.io/news/malaysia/)"
ERROR_MESSAGE_LIMIT = 500


@dataclass(frozen=True)
class OpenAICompletion:
    content: str
    parsed: Any
    diagnostic: dict[str, Any]


class OpenAITransportValueError(ValueError):
    def __init__(self, message: str, diagnostic: dict[str, Any]) -> None:
        super().__init__(message)
        self.openai_diagnostic = diagnostic


def error_diagnostic(error: BaseException) -> dict[str, Any] | None:
    value = getattr(error, "openai_diagnostic", None)
    return value if isinstance(value, dict) else None


def _error_fields(response_body: str) -> dict[str, Any]:
    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else {}
    error = error if isinstance(error, dict) else {}
    failed = error.get("failed_generation")
    failed = failed if isinstance(failed, str) else ""
    return {
        "type": error.get("type", "") if isinstance(error.get("type"), str) else "",
        "code": error.get("code", "") if isinstance(error.get("code"), str) else "",
        "message": error.get("message", "")[:ERROR_MESSAGE_LIMIT] if isinstance(error.get("message"), str) else "",
        "failed_generation_present": bool(failed),
        "failed_generation_length": len(failed),
        "failed_generation_sha256": hashlib.sha256(failed.encode("utf-8")).hexdigest() if failed else "",
    }


def _rate_limit_headers(headers: Any) -> dict[str, str | None]:
    def value(name: str) -> str | None:
        raw = headers.get(name) if headers else None
        return raw.strip() if isinstance(raw, str) and raw.strip() else None

    return {
        "remaining_requests": value("x-ratelimit-remaining-requests"),
        "remaining_tokens": value("x-ratelimit-remaining-tokens"),
        "reset_requests": value("x-ratelimit-reset-requests"),
        "reset_tokens": value("x-ratelimit-reset-tokens"),
        "retry_after": value("retry-after"),
    }


def build_chat_request_body(
    *, model: str, messages: list[dict[str, str]], max_completion_tokens: int,
    reasoning_effort: str, json_schema_name: str, json_schema: dict[str, Any],
) -> dict[str, Any]:
    if not model or max_completion_tokens < 1:
        raise ValueError("model and positive max_completion_tokens are required")
    if reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError("unsupported OpenAI reasoning effort")
    if not json_schema_name or not isinstance(json_schema, dict):
        raise ValueError("strict JSON Schema mode requires a schema name and object")
    return {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_completion_tokens,
        "reasoning_effort": reasoning_effort,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": json_schema_name, "strict": True, "schema": json_schema},
        },
    }


def build_profile_chat_request_body(
    *, profile: ModelProfile, messages: list[dict[str, str]],
    max_completion_tokens: int | None = None, json_schema_name: str,
    json_schema: dict[str, Any],
) -> dict[str, Any]:
    if profile.provider != "openai":
        raise ValueError("OpenAI transport requires an OpenAI model profile")
    if not profile.reasoning_effort:
        raise ValueError("OpenAI model profile requires reasoning_effort")
    token_limit = (
        profile.production_max_tokens
        if max_completion_tokens is None
        else max_completion_tokens
    )
    return build_chat_request_body(
        model=profile.model_id,
        messages=messages,
        max_completion_tokens=token_limit,
        reasoning_effort=profile.reasoning_effort,
        json_schema_name=json_schema_name,
        json_schema=json_schema,
    )


def request_chat_completion(
    *, profile: ModelProfile, messages: list[dict[str, str]], api_key: str,
    max_completion_tokens: int | None = None,
    timeout_seconds: int = 90, max_response_chars: int = 30000,
    json_schema_name: str, json_schema: dict[str, Any],
    schema_error: Callable[[Any], str],
) -> OpenAICompletion:
    if not api_key.strip():
        raise ValueError("OPENAI_API_KEY is missing")
    body = build_profile_chat_request_body(
        profile=profile, messages=messages,
        max_completion_tokens=max_completion_tokens,
        json_schema_name=json_schema_name, json_schema=json_schema,
    )
    request = urllib.request.Request(
        OPENAI_CHAT_COMPLETIONS_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": OPENAI_USER_AGENT},
        method="POST",
    )
    diagnostic: dict[str, Any] = {
        "provider": "openai", "model": profile.model_id,
        "reasoning_effort": profile.reasoning_effort,
        "transport_status": "invalid_envelope", "failure_class": "invalid_envelope",
        "http_status": None, "attempt_count": 1, "elapsed_ms": 0,
        "finish_reason": "other", "content_length": 0,
        "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
        "rate_limit": _rate_limit_headers(None), "json_contract_status": "not_evaluated",
        "json_contract_reason": "", "error": {},
    }
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(max_response_chars + 1).decode("utf-8", errors="replace")
            diagnostic["http_status"] = response.getcode()
            diagnostic["rate_limit"] = _rate_limit_headers(response.headers)
    except urllib.error.HTTPError as error:
        raw = error.read(max_response_chars + 1).decode("utf-8", errors="replace")
        diagnostic.update(http_status=error.code, rate_limit=_rate_limit_headers(error.headers))
        diagnostic["transport_status"] = "rate_limited" if error.code == 429 else "http_error"
        diagnostic["failure_class"] = (
            "rate_limited" if error.code == 429 else
            "authentication_failed" if error.code in {401, 403} else
            "server_error" if error.code >= 500 else "http_error"
        )
        diagnostic["error"] = _error_fields(raw)
        diagnostic["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        try:
            error.openai_diagnostic = diagnostic
        except (AttributeError, TypeError):
            pass
        raise
    except TimeoutError as error:
        diagnostic.update(transport_status="timeout", failure_class="timeout", elapsed_ms=round((time.monotonic() - started) * 1000))
        error.openai_diagnostic = diagnostic
        raise
    except urllib.error.URLError as error:
        diagnostic.update(transport_status="network_error", failure_class="network_error", elapsed_ms=round((time.monotonic() - started) * 1000))
        error.openai_diagnostic = diagnostic
        raise

    diagnostic["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    if len(raw) > max_response_chars:
        diagnostic["failure_class"] = "response_too_large"
        raise OpenAITransportValueError("OpenAI response too long", diagnostic)
    try:
        payload = json.loads(raw)
        choice = payload["choices"][0]
        message = choice["message"]
        content = message.get("content")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        diagnostic["failure_class"] = "invalid_response_envelope"
        raise OpenAITransportValueError("OpenAI response envelope is invalid", diagnostic) from error
    usage = payload.get("usage", {})
    diagnostic["usage"] = {key: usage.get(src) if isinstance(usage.get(src), int) else None for key, src in (("prompt_tokens", "prompt_tokens"), ("completion_tokens", "completion_tokens"), ("total_tokens", "total_tokens"))}
    diagnostic["finish_reason"] = choice.get("finish_reason", "other")
    diagnostic["transport_status"] = "success"
    if diagnostic["finish_reason"] == "length":
        diagnostic.update(json_contract_status="truncated", failure_class="truncated_output")
        raise OpenAITransportValueError("OpenAI response was truncated", diagnostic)
    if not isinstance(content, str) or not content.strip():
        diagnostic.update(json_contract_status="empty", failure_class="empty_output")
        raise OpenAITransportValueError("OpenAI response content is empty", diagnostic)
    diagnostic["content_length"] = len(content)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        diagnostic.update(json_contract_status="invalid_json", failure_class="invalid_json")
        raise OpenAITransportValueError("OpenAI returned invalid JSON", diagnostic) from error
    failure = schema_error(parsed)
    if failure:
        diagnostic.update(json_contract_status="schema_invalid", json_contract_reason=failure, failure_class="schema_invalid")
        raise OpenAITransportValueError(f"OpenAI JSON schema mismatch: {failure}", diagnostic)
    diagnostic.update(json_contract_status="valid", failure_class="none")
    return OpenAICompletion(content, parsed, diagnostic)
