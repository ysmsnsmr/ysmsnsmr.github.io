"""Single request; persist only numeric rate-limit headers."""
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


key = os.environ.get("OPENAI_API_KEY", "").strip()
if not key:
    raise SystemExit("Required secret unavailable")
request = urllib.request.Request(
    "https://api.openai.com/v1/chat/completions",
    data=json.dumps({"model": "gpt-6-luna", "reasoning_effort": "medium",
                     "max_completion_tokens": 1200,
                     "messages": [{"role": "user", "content": "Reply with OK."}]}).encode(),
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
)
try:
    response = urllib.request.build_opener(NoRedirect()).open(request, timeout=20)
except urllib.error.HTTPError as error:
    response = error
except OSError:
    raise SystemExit("Request failed before headers were received") from None

with response:
    result = {}
    for bucket in ("requests", "tokens", "project-tokens"):
        for field in ("limit", "remaining", "reset"):
            name = f"x-ratelimit-{field}-{bucket}"
            value = response.headers.get(name, "").strip()
            pattern = r"[0-9]{1,15}" if field != "reset" else r"(?:[0-9]+(?:\.[0-9]+)?(?:ms|s|m|h|d)){1,5}"
            if len(value) <= 48 and re.fullmatch(pattern, value):
                result[name] = value
    Path(os.environ["PROBE_OUTPUT"]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
