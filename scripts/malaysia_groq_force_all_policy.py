"""Editorial Entry v2 request-cap configuration.

The former force-all priority and lexical gate policy is intentionally gone.
The renderer accepts the legacy CLI flag but always requests selected items in
their JSON order until this cap is reached.
"""

import os


DEFAULT_FORCE_ALL_REQUEST_CAP = 12


def force_all_request_cap() -> int:
    raw = os.environ.get("MALAYSIA_NEWS_GROQ_FORCE_ALL_REQUEST_CAP", "").strip()
    if not raw:
        return DEFAULT_FORCE_ALL_REQUEST_CAP
    try:
        cap = int(raw)
    except ValueError:
        return DEFAULT_FORCE_ALL_REQUEST_CAP
    return cap if cap > 0 else DEFAULT_FORCE_ALL_REQUEST_CAP
