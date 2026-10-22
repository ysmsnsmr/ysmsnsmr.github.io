"""Contract checks for the optional Meta Ads Luna transport."""

import json
import io
import unittest
import urllib.error
from unittest.mock import patch

from meta_ads_personal_feed_presentation import (
    PresentationError,
    _openai_completion,
    request_openai_japanese_backfill,
    request_openai_locale_presentation,
)


class Response:
    def __init__(self, content, finish_reason="stop", refusal=None):
        self.body = json.dumps({"choices": [{"finish_reason": finish_reason, "message": {"content": content, "refusal": refusal}}]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit):
        return self.body


class LunaPresentationTest(unittest.TestCase):
    @staticmethod
    def http_error(status, error_type, error_code, headers=None):
        body = json.dumps({"error": {"type": error_type, "code": error_code, "message": "SECRET RESPONSE"}}).encode()
        return urllib.error.HTTPError("https://api.openai.com/v1/chat/completions", status, "SECRET STATUS", headers or {}, io.BytesIO(body))

    @patch("meta_ads_personal_feed_presentation.urllib.request.urlopen")
    def test_independent_locales_use_medium_strict_json(self, urlopen):
        cases = (
            ("en", {"shortHeadlineEn": "Meta changes ads", "summaryEn": "An ads update."}),
            ("ja", {"shortHeadlineJa": "Meta広告の更新", "summaryJa": "広告が更新された。"}),
        )
        for locale, expected in cases:
            with self.subTest(locale=locale):
                urlopen.return_value = Response(json.dumps(expected, ensure_ascii=False))
                result = request_openai_locale_presentation(
                    api_key="test-key", title="Meta ads", source_context="Source facts",
                    locale=locale, short_headline_max_chars=80, summary_max_chars=360, timeout=1,
                )
                self.assertEqual(result, expected)
                request = urlopen.call_args.args[0]
                payload = json.loads(request.data)
                self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
                self.assertEqual(payload["model"], "gpt-6-luna")
                self.assertEqual(payload["reasoning_effort"], "medium")
                self.assertEqual(payload["max_completion_tokens"], 1200)
                self.assertNotIn("temperature", payload)
                self.assertEqual(payload["response_format"]["type"], "json_schema")

    @patch("meta_ads_personal_feed_presentation.urllib.request.urlopen")
    def test_backfill_preserves_headline_only_input(self, urlopen):
        urlopen.return_value = Response("SHORT_HEADLINE: Meta広告の更新")
        result = request_openai_japanese_backfill(
            api_key="test-key", title="Meta ads", english_summary=None,
            short_headline_max_chars=80, summary_max_chars=360, timeout=1,
        )
        self.assertEqual(result, {"shortHeadlineJa": "Meta広告の更新"})
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertNotIn("response_format", payload)
        self.assertNotIn("ENGLISH_SUMMARY", payload["messages"][1]["content"])

    @patch("meta_ads_personal_feed_presentation.urllib.request.urlopen")
    def test_backfill_translates_saved_english_summary(self, urlopen):
        urlopen.return_value = Response("SHORT_HEADLINE: Meta広告の更新\nSUMMARY: Meta広告が更新された。")
        result = request_openai_japanese_backfill(
            api_key="test-key", title="Meta ads", english_summary="Meta changed its ads.",
            short_headline_max_chars=80, summary_max_chars=360, timeout=1,
        )
        self.assertEqual(result, {
            "shortHeadlineJa": "Meta広告の更新", "summaryJa": "Meta広告が更新された。",
        })
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertIn("ENGLISH_SUMMARY: Meta changed its ads.", payload["messages"][1]["content"])

    @patch("meta_ads_personal_feed_presentation.urllib.request.urlopen")
    def test_truncated_output_is_not_published(self, urlopen):
        urlopen.return_value = Response('{"shortHeadlineEn":"partial"}', "length")
        with self.assertRaises(PresentationError) as caught:
            request_openai_locale_presentation(
                api_key="test-key", title="Meta ads", source_context="Source facts",
                locale="en", short_headline_max_chars=80, summary_max_chars=360, timeout=1,
            )
        self.assertEqual(caught.exception.code, "output_limit")

    @patch("meta_ads_personal_feed_presentation.urllib.request.urlopen")
    def test_refusal_and_content_filter_are_distinct(self, urlopen):
        for response, code in ((Response(None, refusal="SECRET"), "response_refused"),
                               (Response(None, finish_reason="content_filter"), "response_filtered")):
            with self.subTest(code=code):
                urlopen.return_value = response
                with self.assertRaises(PresentationError) as caught:
                    request_openai_japanese_backfill(
                        api_key="test-key", title="Meta ads", english_summary=None,
                        short_headline_max_chars=80, summary_max_chars=360, timeout=1,
                    )
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("SECRET", str(caught.exception))

    @patch("meta_ads_personal_feed_presentation.urllib.request.urlopen")
    def test_quota_429_does_not_retry_or_retain_body(self, urlopen):
        for error_type in ("insufficient_quota", "rate_limit_error"):
            with self.subTest(error_type=error_type):
                urlopen.reset_mock()
                urlopen.side_effect = self.http_error(429, error_type, "credit_balance_exhausted", {
                    "Retry-After": "5", "x-ratelimit-remaining-tokens": "0", "x-ratelimit-reset-tokens": "6m0s",
                    "x-request-id": "SECRET REQUEST ID",
                })
                with self.assertRaises(PresentationError) as caught:
                    _openai_completion(api_key="test-key", messages=[], timeout=1, sleep=lambda _: self.fail("retry"))
                error = caught.exception
                self.assertEqual((error.code, error.attempts, error.provider_error_type, error.provider_error_code),
                                 ("rate_limited_429", 1, error_type, "credit_balance_exhausted"))
                self.assertEqual(error.rate_limit_headers, {
                    "retry_after": "5", "remaining_tokens": "0", "reset_tokens": "6m0s",
                })
                self.assertEqual(urlopen.call_count, 1)
                self.assertNotIn("SECRET", str(error))

    @patch("meta_ads_personal_feed_presentation.urllib.request.urlopen")
    def test_temporary_429_retries_once(self, urlopen):
        urlopen.side_effect = [self.http_error(429, "rate_limit_error", "slow_down", {"Retry-After": "0.5"}), Response("OK")]
        delays = []
        self.assertEqual(_openai_completion(api_key="test-key", messages=[], timeout=1, sleep=delays.append), ("OK", 2))
        self.assertEqual(delays, [0.5])
        self.assertEqual(urlopen.call_count, 2)

    @patch("meta_ads_personal_feed_presentation.urllib.request.urlopen")
    def test_auth_and_long_retry_after_fail_without_retry(self, urlopen):
        for status, error_type, error_code, headers, expected in (
            (401, "invalid_request_error", "invalid_api_key", {}, "auth_401"),
            (429, "rate_limit_error", "slow_down", {"Retry-After": "120"}, "rate_limited_429"),
        ):
            with self.subTest(status=status):
                urlopen.reset_mock()
                urlopen.side_effect = self.http_error(status, error_type, error_code, headers)
                with self.assertRaises(PresentationError) as caught:
                    _openai_completion(api_key="test-key", messages=[], timeout=1, sleep=lambda _: self.fail("retry"))
                self.assertEqual((caught.exception.code, caught.exception.attempts), (expected, 1))
                self.assertEqual(urlopen.call_count, 1)

    @patch("meta_ads_personal_feed_presentation.urllib.request.urlopen")
    def test_temporary_server_retries_but_network_does_not(self, urlopen):
        urlopen.side_effect = [self.http_error(503, "service_unavailable_error", "server_is_overloaded"),
                               self.http_error(503, "service_unavailable_error", "server_is_overloaded")]
        delays = []
        with self.assertRaises(PresentationError) as caught:
            _openai_completion(api_key="test-key", messages=[], timeout=1, sleep=delays.append)
        self.assertEqual((caught.exception.code, caught.exception.attempts), ("http_server_error", 2))
        self.assertEqual(delays, [1.0])
        urlopen.reset_mock()
        urlopen.side_effect = urllib.error.URLError("SECRET NETWORK ERROR")
        with self.assertRaises(PresentationError) as caught:
            _openai_completion(api_key="test-key", messages=[], timeout=1, sleep=lambda _: self.fail("retry"))
        self.assertEqual((caught.exception.code, caught.exception.attempts), ("network_error", 1))
        self.assertEqual(urlopen.call_count, 1)

    @patch("meta_ads_personal_feed_presentation.urllib.request.urlopen")
    def test_invalid_json_shape_and_length_are_separate(self, urlopen):
        for response, code in (
            (Response("not json"), "response_invalid_json"),
            (Response('{"shortHeadlineEn":"Only one field"}'), "response_invalid_shape"),
            (Response(json.dumps({"shortHeadlineEn": "a" * 81, "summaryEn": "Valid"})), "short_headline_invalid"),
            (Response(json.dumps({"shortHeadlineEn": "Valid", "summaryEn": "a" * 361})), "summary_invalid"),
        ):
            with self.subTest(code=code):
                urlopen.return_value = response
                with self.assertRaises(PresentationError) as caught:
                    request_openai_locale_presentation(
                        api_key="test-key", title="Meta ads", source_context="Source facts",
                        locale="en", short_headline_max_chars=80, summary_max_chars=360, timeout=1,
                    )
                self.assertEqual(caught.exception.code, code)

    @patch("meta_ads_personal_feed_presentation.urllib.request.urlopen")
    def test_validation_failure_keeps_request_attempt_count(self, urlopen):
        urlopen.side_effect = [self.http_error(429, "rate_limit_error", "slow_down", {"Retry-After": "0"}),
                               Response("not json")]
        with self.assertRaises(PresentationError) as caught:
            request_openai_locale_presentation(
                api_key="test-key", title="Meta ads", source_context="Source facts",
                locale="en", short_headline_max_chars=80, summary_max_chars=360, timeout=1,
            )
        self.assertEqual((caught.exception.code, caught.exception.attempts), ("response_invalid_json", 2))


if __name__ == "__main__":
    unittest.main()
