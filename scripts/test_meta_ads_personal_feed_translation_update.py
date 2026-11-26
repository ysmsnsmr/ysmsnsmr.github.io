import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update_meta_ads_headline_translations as updater


class ScheduledTranslationTest(unittest.TestCase):
    def test_all_pending_articles_and_checkpoint_on_rate_limit(self):
        root = Path(__file__).resolve().parent.parent
        feed = json.loads((root / "meta-ads-updates/personal-feed.json").read_text())
        feed["items"] = feed["items"][:5]
        for fail in (False, True):
            with self.subTest(rate_limit=fail), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp) / "meta-ads-updates"
                folder.mkdir()
                (folder / "personal-feed.json").write_text(json.dumps(feed))
                overlay = folder / "headline-translations.json"
                overlay.write_text('{"schemaVersion":"meta-ads-headline-translations/v1","items":{}}')
                real_path = Path
                calls = []

                def generate(**kwargs):
                    calls.append(kwargs)
                    if fail and len(calls) == 5:
                        raise updater.translation.presentation.PresentationError("rate_limited_429")
                    return "translated"

                with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch.object(
                    updater, "Path", side_effect=lambda value: real_path(tmp) / value
                ), patch.object(updater.translation, "translate_headline", side_effect=generate):
                    updater.main()
                result = json.loads(overlay.read_text())["items"]
                self.assertEqual(len(calls), 5 if fail else 15)
                self.assertEqual(len(result), 2 if fail else 5)
                self.assertTrue(all(r["status"] == "machine" for r in result[feed["items"][0]["id"]].values()))
