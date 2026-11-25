"""Manual experiment, on a temporary branch only. No feed/state writes."""
import io
import json
import os
from pathlib import Path
from unittest.mock import patch
import urllib.request

import meta_ads_headline_translations as translations

IDS = (
    "meta-business-help-discovered-207f30d0c75941ff72df",
    "meta-business-help-discovered-a6fbbdd05256e71d50d2",
    "social-media-today-meta-ads-3d214e350b57f2ef67ea",
)

def main():
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise SystemExit("OPENAI_API_KEY is not configured")
    feed = json.loads(Path("meta-ads-updates/personal-feed.json").read_text(encoding="utf-8"))
    selected = {item["id"]: item for item in feed["items"] if item["id"] in IDS}
    if set(selected) != set(IDS):
        raise SystemExit("A selected feed item is missing")
    feed["items"] = [selected[item_id] for item_id in IDS]
    usage = []
    urlopen = urllib.request.urlopen

    def capture(request, **kwargs):
        with urlopen(request, **kwargs) as response:
            body = response.read(50001)
        try:
            data = json.loads(body)
            record = data.get("usage", {})
            usage.append({name: record.get(name) for name in ("prompt_tokens", "completion_tokens", "total_tokens")})
        except (ValueError, AttributeError):
            pass
        return io.BytesIO(body)

    with patch.object(urllib.request, "urlopen", capture):
        state = translations.build_state(
            feed, None,
            generate=lambda title, locale: translations.translate_headline(api_key=key, title=title, locale=locale),
        )
    results = []
    for item in feed["items"]:
        results.append({"id": item["id"], "originalTitle": item["title"],
                        "englishHeadline": item["presentation"]["locales"]["en"]["shortHeadline"],
                        "japaneseHeadline": item["presentation"]["locales"]["ja"]["shortHeadline"],
                        "translations": state["items"][item["id"]]})
    output = {"model": "gpt-6-luna", "reasoningEffort": "medium", "items": results, "usage": usage}
    Path(os.environ["PROBE_OUTPUT"]).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Probe complete: 3 items, 3 locales; results and usage in artifact.")

if __name__ == "__main__":
    main()
