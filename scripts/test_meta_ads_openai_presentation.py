"""Contract checks for the optional Meta Ads Luna transport."""

import json
import unittest
from unittest.mock import patch

from meta_ads_personal_feed_presentation import (
    PresentationError,
    request_openai_japanese_backfill,
    request_openai_locale_presentation,
)


class Response:
    def __init__(self, content, finish_reason="stop"):
        self.body = json.dumps({"choices": [{"finish_reason": finish_reason, "message": {"content": content}}]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit):
        return self.body


class LunaPresentationTest(unittest.TestCase):
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
        with self.assertRaises(PresentationError):
            request_openai_locale_presentation(
                api_key="test-key", title="Meta ads", source_context="Source facts",
                locale="en", short_headline_max_chars=80, summary_max_chars=360, timeout=1,
            )


if __name__ == "__main__":
    unittest.main()
