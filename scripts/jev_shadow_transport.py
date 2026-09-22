"""Minimal shared transport for artifact-only Jev shadow experiments."""
from __future__ import annotations

import json
import platform
import re
import sys
import urllib.error
import urllib.request
from typing import Any


ENDPOINT = "https://api.typesafe.ai/v1/systemone"
SDK_NAME = "typesafe-sdk"
SDK_VERSION = "artifact-runner"
MAX_RESPONSE_BYTES = 262_144
MAX_ERROR_CLASSIFICATION_BYTES = 16_384


class JevRequestError(RuntimeError):
    """A safe failure category, intentionally without response content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject every redirect before urllib can forward request headers."""

    def redirect_request(
        self,
        request: urllib.request.Request,
        fp: Any,
        code: int,
        message: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request:
        del request, fp, code, message, headers, newurl
        raise JevRequestError("redirect_blocked")


def _safe_http_error_detail(error: urllib.error.HTTPError) -> str | None:
    """Extract only a bounded, identifier-shaped error code or type."""
    try:
        raw = error.read(MAX_ERROR_CLASSIFICATION_BYTES)
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    nested = payload.get("error")
    if not isinstance(nested, dict):
        nested = payload
    for field in ("code", "type"):
        value = nested.get(field)
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", value):
            return value
    return None


def post_jev_request(payload: dict[str, Any], api_key: str, timeout_seconds: float) -> dict[str, Any]:
    """Call Jev without environment proxies or persisted response bodies."""
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=encoded,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"{SDK_NAME}/{SDK_VERSION}",
            "X-TypeSafe-SDK": f"{SDK_NAME}/{SDK_VERSION}",
            "X-TypeSafe-Runtime": (
                f"python/{platform.python_version()} ({sys.platform}; {platform.machine()})"
            ),
        },
        method="POST",
    )
    # This request carries a bearer token to one fixed endpoint.  Do not follow
    # a redirect, even to the same host, because urllib may retain Authorization
    # when it constructs the redirected request.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirectHandler(),
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get_content_type().lower()
            if content_type != "application/json":
                raise JevRequestError("unexpected_content_type")
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except JevRequestError:
        raise
    except urllib.error.HTTPError as error:
        detail = _safe_http_error_detail(error)
        suffix = f"_{detail}" if detail else ""
        raise JevRequestError(f"http_status_{error.code}{suffix}") from error
    except urllib.error.URLError as error:
        raise JevRequestError("network_error") from error
    except TimeoutError as error:
        raise JevRequestError("timeout") from error

    if len(body) > MAX_RESPONSE_BYTES:
        raise JevRequestError("response_too_large")
    try:
        response_json = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise JevRequestError("invalid_json_response") from error
    if not isinstance(response_json, dict):
        raise JevRequestError("invalid_json_response")
    return response_json
