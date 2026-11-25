from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema.exceptions import ValidationError
import meta_ads_headline_translations as translations
import meta_ads_personal_feed_presentation as presentation


class HeadlineTranslationsTest(unittest.TestCase):
    def setUp(self):
        feed_path = Path(__file__).resolve().parent.parent / "meta-ads-updates/personal-feed.json"
        self.feed = json.loads(feed_path.read_text(encoding="utf-8"))
        self.feed["items"] = self.feed["items"][:1]
        self.item_id = self.feed["items"][0]["id"]
        self.now = "2026-11-25T00:00:00Z"

    def test_independent_state_does_not_change_english_japanese(self):
        original = copy.deepcopy(self.feed)
        calls = []
        def generate(title, locale):
            calls.append((title, locale))
            return {"zh-Hans": "广告更新", "es": "Actualización de anuncios", "ko": "광고 업데이트"}[locale]
        state = translations.build_state(self.feed, None, generate=generate, now=self.now)
        self.assertEqual(self.feed, original)
        self.assertEqual(set(state["items"][self.item_id]), set(translations.LOCALES))
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(record["status"] == "machine" for record in state["items"][self.item_id].values()))
        again = translations.build_state(self.feed, state, generate=lambda *_: self.fail("unexpected retry"), now=self.now)
        self.assertEqual(state, again)

    def test_failure_is_isolated_and_retry_only_missing(self):
        def generate(title, locale):
            if locale == "es":
                raise presentation.PresentationError("rate_limited_429")
            return "translated"
        state = translations.build_state(self.feed, None, generate=generate, now=self.now)
        self.assertEqual(state["items"][self.item_id]["es"]["error"], "rate_limited_429")
        self.assertIsNone(state["items"][self.item_id]["es"]["value"])
        calls = []
        recovered = translations.build_state(self.feed, state, generate=lambda title, locale: calls.append(locale) or "recuperado", now=self.now)
        self.assertEqual(calls, ["es"])
        self.assertEqual(recovered["items"][self.item_id]["es"]["status"], "machine")
        self.assertEqual(recovered["items"][self.item_id]["ko"], state["items"][self.item_id]["ko"])

    def test_stale_input_is_regenerated(self):
        state = translations.build_state(self.feed, None, generate=lambda *_: "old", now=self.now)
        self.feed["items"][0]["presentation"]["locales"]["en"]["shortHeadline"] = "Changed headline"
        calls = []
        result = translations.build_state(self.feed, state, generate=lambda title, locale: calls.append(locale) or "new", now=self.now)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["items"][self.item_id]["es"]["value"], "new")

    def test_contract_and_atomic_save(self):
        state = translations.build_state(self.feed, None, generate=lambda *_: "headline", now=self.now)
        invalid = copy.deepcopy(state)
        invalid["items"][self.item_id]["es"]["summary"] = "not allowed"
        with self.assertRaises(ValidationError):
            translations.validate_state(invalid)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            translations.save_state(path, state)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), state)
            with self.assertRaises(ValidationError):
                translations.save_state(path, invalid)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), state)

    def test_openai_output_validation_and_safe_failure(self):
        with patch.object(presentation, "_openai_completion", return_value=('{"headline":"Hola"}', 1)) as request:
            self.assertEqual(translations.translate_headline(api_key="key", title="test", locale="es"), "Hola")
            self.assertIn("untrusted", request.call_args.kwargs["messages"][0]["content"])
            self.assertTrue(request.call_args.kwargs["response_format"]["json_schema"]["strict"])
        for content, code in [("invalid", "response_invalid_json"), ('{"headline":""}', "short_headline_invalid"), ('{"other":"x"}', "response_invalid_shape")]:
            with self.subTest(code=code), patch.object(presentation, "_openai_completion", return_value=(content, 1)):
                with self.assertRaises(presentation.PresentationError) as error:
                    translations.translate_headline(api_key="key", title="test", locale="es")
                self.assertEqual(error.exception.code, code)

    def test_provider_failures_are_safe_and_do_not_affect_other_languages(self):
        for code in ("api_key_unavailable", "auth_401", "rate_limited_429", "network_error", "http_server_error", "output_limit", "response_refused"):
            def generate(title, locale):
                if locale == "ko":
                    raise presentation.PresentationError(code, provider_error_code="do_not_persist")
                return "headline"
            with self.subTest(code=code):
                state = translations.build_state(self.feed, None, generate=generate, now=self.now)
                self.assertEqual(state["items"][self.item_id]["ko"]["error"], code)
                self.assertEqual(state["items"][self.item_id]["es"]["status"], "machine")
                self.assertNotIn("do_not_persist", json.dumps(state))

    def test_invalid_input_and_unexpected_failure_do_not_modify_feed(self):
        original = copy.deepcopy(self.feed)
        with self.assertRaises(RuntimeError):
            translations.build_state(self.feed, None, generate=lambda *_: (_ for _ in ()).throw(RuntimeError("failed")), now=self.now)
        self.assertEqual(self.feed, original)
        self.feed["items"][0]["presentation"]["locales"]["en"]["unexpected"] = "invalid"
        with self.assertRaises(ValidationError):
            translations.build_state(self.feed, None, generate=lambda *_: "headline", now=self.now)


if __name__ == "__main__":
    unittest.main()
