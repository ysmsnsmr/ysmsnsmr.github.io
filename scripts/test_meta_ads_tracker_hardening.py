from __future__ import annotations

import copy
import io
import socket
import tempfile
import unittest
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from defusedxml.common import DefusedXmlException

from meta_ads_tracker_collect import (
    _RestrictedRedirectHandler,
    _parse_rss,
    _parse_sdk,
    _request,
    _validate_transport_url,
    SourceFetchError,
    collect_and_write,
)
from meta_ads_tracker_contract import (
    ContractError,
    DEFAULT_SOURCE_CONFIG,
    load_and_validate_source_config,
    validate_source_config,
)


PUBLIC_ADDRESS = "93.184.216.34"


def global_resolver(_hostname: str, _port: int, **_kwargs: object) -> list[tuple[object, ...]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_ADDRESS, 443))]


class FakeResponse:
    def __init__(self, body: bytes, content_type: str, *, content_length: str | None = None, url: str) -> None:
        self._body = io.BytesIO(body)
        self._url = url
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, amount: int = -1) -> bytes:
        return self._body.read(amount)

    def geturl(self) -> str:
        return self._url


class FakeOpener:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response

    def open(self, _request: Request, timeout: float) -> FakeResponse:
        self.timeout = timeout
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class MetaAdsTransportHardeningTest(unittest.TestCase):
    def setUp(self) -> None:
        config = load_and_validate_source_config()
        self.rss_source = copy.deepcopy(config["sources"][0])
        self.sdk_source = copy.deepcopy(config["sources"][3])

    def test_v2_config_declares_bounded_transport_for_enabled_sources(self) -> None:
        self.assertEqual(self.rss_source["transport"], {
            "allowedFetchHosts": ["about.fb.com"],
            "maxResponseBytes": 1048576,
            "maxRedirects": 3,
            "maxItems": 250,
        })
        self.assertEqual(self.sdk_source["transport"]["allowedFetchHosts"], ["api.github.com"])
        self.assertEqual(self.sdk_source["transport"]["maxItems"], 100)

    def test_config_rejects_transport_hosts_and_limits_outside_the_contract(self) -> None:
        config = load_and_validate_source_config()
        invalid = copy.deepcopy(config)
        invalid["sources"][0]["transport"]["allowedFetchHosts"] = ["127.0.0.1"]
        with self.assertRaisesRegex(ContractError, "DNS hostname"):
            validate_source_config(invalid)

        invalid = copy.deepcopy(config)
        invalid["sources"][0]["transport"]["maxResponseBytes"] = 16 * 1024 * 1024 + 1
        with self.assertRaisesRegex(ContractError, "maxResponseBytes"):
            validate_source_config(invalid)

    def test_transport_rejects_unsafe_urls_and_non_global_resolution(self) -> None:
        for unsafe in (
            "http://about.fb.com/news/feed/",
            "https://user:password@about.fb.com/news/feed/",
            "https://127.0.0.1/news/feed/",
            "https://about.fb.com:444/news/feed/",
            "https://untrusted.example.test/news/feed/",
        ):
            with self.subTest(url=unsafe), self.assertRaises(ContractError):
                _validate_transport_url(unsafe, self.rss_source, global_resolver)

        def loopback_resolver(_hostname: str, _port: int, **_kwargs: object) -> list[tuple[object, ...]]:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

        with self.assertRaisesRegex(ContractError, "non-global"):
            _validate_transport_url(self.rss_source["fetchUrl"], self.rss_source, loopback_resolver)
        _validate_transport_url(self.rss_source["fetchUrl"], self.rss_source, global_resolver)

    def test_redirect_handler_allows_the_configured_host_and_rejects_escape_or_excess(self) -> None:
        headers = Message()
        request = Request(self.rss_source["fetchUrl"])
        handler = _RestrictedRedirectHandler(self.rss_source, global_resolver)
        redirected = handler.redirect_request(request, None, 302, "Found", headers, "/news/redirected/")
        self.assertEqual(redirected.full_url, "https://about.fb.com/news/redirected/")
        with self.assertRaisesRegex(ContractError, "not allowed"):
            handler.redirect_request(request, None, 302, "Found", headers, "https://evil.example.test/")

        limited = copy.deepcopy(self.rss_source)
        limited["transport"]["maxRedirects"] = 1
        handler = _RestrictedRedirectHandler(limited, global_resolver)
        handler.redirect_request(request, None, 302, "Found", headers, "/one/")
        with self.assertRaisesRegex(ContractError, "redirect limit"):
            handler.redirect_request(request, None, 302, "Found", headers, "/two/")

    def test_request_disables_proxy_and_accepts_charset_content_type(self) -> None:
        response = FakeResponse(
            b"<rss><channel /></rss>",
            "application/rss+xml; charset=UTF-8",
            url=self.rss_source["fetchUrl"],
        )
        opener = FakeOpener(response)
        with patch("meta_ads_tracker_collect.socket.getaddrinfo", global_resolver), patch(
            "meta_ads_tracker_collect.urllib.request.build_opener", return_value=opener
        ) as build_opener:
            body, content_type = _request(self.rss_source, 2.5)
        self.assertEqual(body, "<rss><channel /></rss>")
        self.assertEqual(content_type, "application/rss+xml")
        handlers = build_opener.call_args.args
        self.assertEqual(handlers[0].proxies, {})

    def test_request_rejects_content_type_and_declared_or_streamed_size_overflow(self) -> None:
        cases = (
            FakeResponse(b"{}", "text/html", url=self.rss_source["fetchUrl"]),
            FakeResponse(b"{}", "application/rss+xml", content_length="1048577", url=self.rss_source["fetchUrl"]),
            FakeResponse(b"x" * 9, "application/rss+xml", url=self.rss_source["fetchUrl"]),
        )
        for index, response in enumerate(cases):
            source = copy.deepcopy(self.rss_source)
            if index == 2:
                source["transport"]["maxResponseBytes"] = 8
            with self.subTest(case=index), patch("meta_ads_tracker_collect.socket.getaddrinfo", global_resolver), patch(
                "meta_ads_tracker_collect.urllib.request.build_opener", return_value=FakeOpener(response)
            ), self.assertRaises(ContractError):
                _request(source, 1)

    def test_request_retries_only_safe_transient_statuses_and_logs_no_response_content(self) -> None:
        first = FakeOpener(
            HTTPError(self.rss_source["fetchUrl"], 415, "unsupported", {"Retry-After": "4"}, None)
        )
        second = FakeOpener(
            FakeResponse(b"<rss><channel /></rss>", "application/rss+xml", url=self.rss_source["fetchUrl"])
        )
        delays: list[float] = []
        with patch("meta_ads_tracker_collect.socket.getaddrinfo", global_resolver), patch(
            "meta_ads_tracker_collect.urllib.request.build_opener", side_effect=[first, second]
        ) as build_opener:
            body, content_type = _request(self.rss_source, 1, sleep=delays.append)
        self.assertEqual((body, content_type), ("<rss><channel /></rss>", "application/rss+xml"))
        self.assertEqual(delays, [4.0])
        self.assertEqual(build_opener.call_count, 2)

    def test_request_does_not_retry_permanent_status_or_expose_error_body(self) -> None:
        blocked = FakeOpener(HTTPError(self.rss_source["fetchUrl"], 403, "secret response body", {}, None))
        with patch("meta_ads_tracker_collect.socket.getaddrinfo", global_resolver), patch(
            "meta_ads_tracker_collect.urllib.request.build_opener", return_value=blocked
        ) as build_opener, self.assertRaises(SourceFetchError) as error:
            _request(self.rss_source, 1, sleep=lambda _delay: None)
        self.assertEqual(error.exception.source_id, self.rss_source["id"])
        self.assertEqual(error.exception.reason, "http_status=403")
        self.assertEqual(error.exception.attempts, 1)
        self.assertNotIn("secret response body", str(error.exception))
        self.assertEqual(build_opener.call_count, 1)

    def test_safe_parsers_reject_dtd_and_item_overflow(self) -> None:
        with self.assertRaises(DefusedXmlException):
            _parse_rss("<!DOCTYPE rss [<!ENTITY test 'blocked'>]><rss><channel><item><title>&test;</title></item></channel></rss>", 250)
        rss = "<rss><channel>" + "".join(
            f"<item><title>{index}</title><link>https://about.fb.com/news/{index}/</link></item>"
            for index in range(251)
        ) + "</channel></rss>"
        with self.assertRaisesRegex(ContractError, "item limit"):
            _parse_rss(rss, 250)
        with self.assertRaisesRegex(ContractError, "item limit"):
            _parse_sdk(
                '[{"tag_name":"v1","html_url":"https://github.com/facebook/release/1"},'
                '{"tag_name":"v2","html_url":"https://github.com/facebook/release/2"}]',
                1,
            )

    def test_fetch_failure_leaves_existing_candidate_and_state_bytes_untouched(self) -> None:
        def failing_fetch(_source: dict, _timeout: float) -> tuple[str, str]:
            raise URLError("response body must not be persisted")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "candidate.json"
            state = root / "state.json"
            original_output = b'{"existing":"candidate"}\n'
            original_state = b'{"existing":"state"}\n'
            output.write_bytes(original_output)
            state.write_bytes(original_state)
            with self.assertRaises(URLError):
                collect_and_write(
                    DEFAULT_SOURCE_CONFIG,
                    state,
                    output,
                    1,
                    now=datetime(2026, 8, 22, tzinfo=timezone.utc),
                    fetch_body=failing_fetch,
                )
            self.assertEqual(output.read_bytes(), original_output)
            self.assertEqual(state.read_bytes(), original_state)


if __name__ == "__main__":
    unittest.main()
