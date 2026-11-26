"""Bounded translation update for the already validated published feed."""
import json
import os
from pathlib import Path

import meta_ads_headline_translations as translation


def main():
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return
    path = Path("meta-ads-updates/headline-translations.json")
    previous = json.loads(path.read_text(encoding="utf-8"))
    translation.validate_state(previous)
    feed = json.loads(Path("meta-ads-updates/personal-feed.json").read_text(encoding="utf-8"))
    translation._validate(feed, translation.FEED_SCHEMA)
    live = {item["id"] for item in feed["items"]}
    cached = {key: value for key, value in previous["items"].items() if key in live}
    candidates = []
    for item in feed["items"]:
        records = cached.get(item["id"], {})
        if any(records.get(locale, {}).get("status") != "machine"
               or records[locale]["inputHash"] != translation.input_hash(locale, item["title"])
               for locale in translation.LOCALES):
            candidates.append(item)
    # Give untouched items priority over persistent failures.
    candidates.sort(key=lambda item: item["id"] in cached)
    updated = translation.build_state(
        {**feed, "items": candidates[:3]}, previous,
        generate=lambda title, locale: translation.translate_headline(
            api_key=key, title=title, locale=locale, timeout=15, max_attempts=1),
    )
    result = {**previous, "items": {**cached, **updated["items"]}}
    if result != previous:
        translation.save_state(path, result)


if __name__ == "__main__":
    main()
