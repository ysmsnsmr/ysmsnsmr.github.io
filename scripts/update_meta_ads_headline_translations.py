"""Bounded translation update for the already validated published feed."""
import json
import os
import time
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
    result = {**previous, "items": cached}
    if result != previous:
        translation.save_state(path, result)
    deadline = time.monotonic() + 8 * 60
    stop = None

    def generate(title, locale):
        nonlocal stop
        if stop:
            raise translation.presentation.PresentationError(stop)
        try:
            return translation.translate_headline(
                api_key=key, title=title, locale=locale, timeout=15, max_attempts=1)
        except translation.presentation.PresentationError as error:
            if error.code in {"auth_401", "permission_403", "rate_limited_429"}:
                stop = error.code
            raise

    for index, item in enumerate(candidates):
        if stop or time.monotonic() >= deadline:
            print(f"Headline translation deferred: {len(candidates) - index} articles ({stop or 'time budget'})")
            break
        update = translation.build_state({**feed, "items": [item]}, previous, generate=generate)
        result["items"].update(update["items"])
        translation.save_state(path, result)


if __name__ == "__main__":
    main()
