"""Experimental branch only: generate at most 291 missing headlines."""
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock

import meta_ads_headline_translations as t


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise SystemExit("Required secret unavailable")
    urllib.request.install_opener(urllib.request.build_opener(NoRedirect()))
    feed = json.loads(Path("meta-ads-updates/personal-feed.json").read_text())
    previous = json.loads(Path("meta-ads-updates/headline-translations.json").read_text())
    out = Path(os.environ["PROBE_OUTPUT"])
    stop = Event()
    lock = Lock()
    attempts = 0

    def generate(title, locale):
        nonlocal attempts
        with lock:
            if stop.is_set() or attempts >= 291:
                raise t.presentation.PresentationError("unknown")
            attempts += 1
        try:
            return t.translate_headline(title=title, locale=locale, api_key=key,
                                        timeout=15, max_attempts=1)
        except t.presentation.PresentationError as error:
            if error.code in {"auth_401", "permission_403", "rate_limited_429"}:
                stop.set()
            raise

    t._validate(feed, t.FEED_SCHEMA)
    t.validate_state(previous)
    result = {**previous, "items": {}}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for offset in range(0, len(feed["items"]), 8):
            chunk = feed["items"][offset:offset + 8]
            results = pool.map(lambda item: t.build_state(
                {**feed, "items": [item]}, previous, generate=generate), chunk)
            for partial in results:
                result["items"].update(partial["items"])
            t.save_state(out, result)
    from collections import Counter
    counts = Counter(r["error"] for group in result["items"].values()
                     for r in group.values() if r["status"] != "machine")
    print(f"Requests: {attempts}; missing by safe code: {dict(counts)}")


if __name__ == "__main__":
    main()
