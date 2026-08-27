"""Small shared Groq transport with safe, artifact-friendly diagnostics."""

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from malaysia_groq_model_profiles import ModelProfile


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_USER_AGENT = "ysmsnsmr-malaysia-news/0.1 (+https://ysmsnsmr.github.io/news/malaysia/)"
ERROR_MESSAGE_LIMIT = 500
SAFE_CONTRACT_REASONS = frozenset(
    {
        "root_shape",
        "summary_shape",
        "summary_value",
        "entry_shape",
        "editorial_entry_shape",
        "editorial_entry_value",
        "verdict",
        "issues",
        "reviewed_entry",
    }
)


@dataclass(frozen=True)
class ChatCompletion:
    content: str
    parsed: Any
    diagnostic: dict[str, Any]


class GroqTransportValueError(ValueError):
    def __init__(self, message: str, diagnostic: dict[str, Any]) -> None:
        super().__init__(message)
        self.groq_diagnostic = diagnostic


def _clean_error_message(value: Any) -> str:
    return value.strip()[:ERROR_MESSAGE_LIMIT] if isinstance(value, str) else ""


def _safe_contract_reason(value: Any) -> str:
    return value if isinstance(value, str) and value in SAFE_CONTRACT_REASONS else "unknown"


def _rate_limit_headers(headers: Any) -> dict[str, Any]:
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


def empty_diagnostic() -> dict[str, Any]:
    return {
        "transport_status": "invalid_envelope",
        "http_status": None,
        "attempt_count": 1,
        "elapsed_ms": 0,
        "finish_reason": "other",
        "content_length": 0,
        "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
        "rate_limit": _rate_limit_headers(None),
        "json_contract_status": "not_evaluated",
        "json_contract_reason": "",
        "error": {
            "type": "",
            "code": "",
            "message": "",
            "failed_generation_present": False,
            "failed_generation_length": 0,
            "failed_generation_sha256": "",
        },
    }


def error_diagnostic(error: BaseException) -> dict[str, Any] | None:
    value = getattr(error, "groq_diagnostic", None)
    return value if isinstance(value, dict) else None


def attach_diagnostic(error: BaseException, diagnostic: dict[str, Any]) -> None:
    try:
        setattr(error, "groq_diagnostic", diagnostic)
    except (AttributeError, TypeError):
        pass


def build_chat_request_body(
    profile: ModelProfile,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    json_schema_name: str | None = None,
    json_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": profile.model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if profile.reasoning_mode == "low_hidden":
        body["include_reasoning"] = False
        body["reasoning_effort"] = "low"
    elif profile.reasoning_mode == "hidden":
        body["reasoning_format"] = "hidden"

    if profile.response_mode == "json_schema_strict":
        if not json_schema_name or not isinstance(json_schema, dict):
            raise ValueError("strict JSON Schema mode requires a schema name and object")
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": json_schema_name,
                "strict": True,
                "schema": json_schema,
            },
        }
    elif profile.response_mode == "json_object":
        body["response_format"] = {"type": "json_object"}
    else:
        raise ValueError(f"unsupported response mode: {profile.response_mode}")
    return body


def _strip_json_code_fence(content: str) -> str:
    text = content.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


def _usage(value: Any) -> dict[str, int | None]:
    usage = value if isinstance(value, dict) else {}
    return {
        "prompt_tokens": usage.get("prompt_tokens") if isinstance(usage.get("prompt_tokens"), int) else None,
        "completion_tokens": usage.get("completion_tokens") if isinstance(usage.get("completion_tokens"), int) else None,
        "total_tokens": usage.get("total_tokens") if isinstance(usage.get("total_tokens"), int) else None,
    }


def _error_fields(response_body: str) -> dict[str, Any]:
    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else {}
    error = error if isinstance(error, dict) else {}
    failed_generation = error.get("failed_generation")
    failed_text = failed_generation if isinstance(failed_generation, str) else ""
    return {
        "type": _clean_error_message(error.get("type")),
        "code": _clean_error_message(error.get("code")),
        "message": _clean_error_message(error.get("message")),
        "failed_generation_present": bool(failed_text),
        "failed_generation_length": len(failed_text),
        "failed_generation_sha256": hashlib.sha256(failed_text.encode("utf-8")).hexdigest() if failed_text else "",
    }


def request_chat_completion(
    *,
    profile: ModelProfile,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
    max_response_chars: int,
    json_schema_name: str,
    json_schema: dict[str, Any],
    schema_error: Callable[[Any], str],
    api_key: str,
) -> ChatCompletion:
    diagnostic = empty_diagnostic()
    body = build_chat_request_body(
        profile,
        messages,
        temperature,
        max_tokens,
        json_schema_name,
        json_schema,
    )
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
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read(max_response_chars + 1).decode("utf-8", errors="replace")
            diagnostic["http_status"] = response.getcode()
            diagnostic["rate_limit"] = _rate_limit_headers(response.headers)
    except urllib.error.HTTPError as error:
        response_body = error.read(max_response_chars + 1).decode("utf-8", errors="replace")
        diagnostic["http_status"] = error.code
        diagnostic["rate_limit"] = _rate_limit_headers(error.headers)
        diagnostic["transport_status"] = "rate_limited" if error.code == 429 else "http_error"
        diagnostic["error"] = _error_fields(response_body)
        diagnostic["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        attach_diagnostic(error, diagnostic)
        raise
    except TimeoutError as error:
        diagnostic["transport_status"] = "timeout"
        diagnostic["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        attach_diagnostic(error, diagnostic)
        raise
    except urllib.error.URLError as error:
        diagnostic["transport_status"] = "network_error"
        diagnostic["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        attach_diagnostic(error, diagnostic)
        raise

    diagnostic["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    if len(response_body) > max_response_chars:
        raise GroqTransportValueError("Groq response too long", diagnostic)
    try:
        payload = json.loads(response_body)
        choices = payload.get("choices") if isinstance(payload, dict) else None
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        message = choice.get("message") if isinstance(choice, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
    except (AttributeError, IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise GroqTransportValueError("Groq response envelope is invalid", diagnostic) from error
    diagnostic["usage"] = _usage(payload.get("usage") if isinstance(payload, dict) else None)
    diagnostic["finish_reason"] = choice.get("finish_reason") if isinstance(choice, dict) and isinstance(choice.get("finish_reason"), str) else "other"
    if not isinstance(content, str) or not content.strip():
        diagnostic["json_contract_status"] = "empty"
        raise GroqTransportValueError("Groq response content is empty", diagnostic)
    diagnostic["content_length"] = len(content)
    if len(content) > max_response_chars:
        raise GroqTransportValueError("Groq message content too long", diagnostic)
    if diagnostic["finish_reason"] == "length":
        diagnostic["json_contract_status"] = "truncated"
        raise GroqTransportValueError("Groq response was truncated", diagnostic)
    try:
        parsed = json.loads(_strip_json_code_fence(content))
    except json.JSONDecodeError as error:
        diagnostic["json_contract_status"] = "invalid_json"
        raise GroqTransportValueError(str(error), diagnostic) from error
    schema_failure = schema_error(parsed)
    if schema_failure:
        diagnostic["json_contract_status"] = "schema_invalid"
        diagnostic["json_contract_reason"] = _safe_contract_reason(schema_failure)
        if profile.response_mode == "json_schema_strict":
            raise GroqTransportValueError(f"Groq JSON schema mismatch: {schema_failure}", diagnostic)
        diagnostic["transport_status"] = "success"
        return ChatCompletion(content, parsed, diagnostic)
    diagnostic["transport_status"] = "success"
    diagnostic["json_contract_status"] = "valid"
    return ChatCompletion(content, parsed, diagnostic)
