#!/usr/bin/env python3
"""Header-only, artifact-only observation of official Meta Developers pages."""
from __future__ import annotations

import argparse, json, sys, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

USER_AGENT = "ysmsnsmr-meta-ads-official-canary/1.0 (+https://github.com/ysmsnsmr/ysmsnsmr.github.io)"
Fetch = Callable[[str, str, float], tuple[int, str, dict[str, str]]]

def request_headers(url: str, method: str, timeout: float) -> tuple[int, str, dict[str, str]]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html;q=0.9,*/*;q=0.1"}
    if method == "GET": headers["Range"] = "bytes=0-0"
    request = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.geturl(), dict(response.headers.items())
    except urllib.error.HTTPError as error:
        return error.code, error.geturl(), dict(error.headers.items()) if error.headers else {}

def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or set(config) != {"schemaVersion", "policies", "sources"} or config["schemaVersion"] != "meta-ads-official-canaries/v1":
        raise ValueError("invalid canary config schema")
    if config["policies"] != {"artifactOnly": True, "persistRawResponseBody": False, "failureAction": "observe_only"}:
        raise ValueError("canary policies must remain artifact-only and body-free")
    ids=set()
    for source in config["sources"]:
        if not isinstance(source,dict) or set(source) != {"id","name","url","expectedContentTypes"} or not source["id"] or source["id"] in ids:
            raise ValueError("invalid or duplicate canary source")
        ids.add(source["id"]); parsed=urlparse(source["url"])
        if parsed.scheme != "https" or parsed.hostname != "developers.facebook.com" or not source["expectedContentTypes"]:
            raise ValueError("canary source must be an HTTPS Meta Developers page")
    return config

def probe(source: dict[str, Any], timeout: float, fetch: Fetch = request_headers) -> dict[str, Any]:
    method="HEAD"
    try:
        status, final, headers=fetch(source["url"],method,timeout)
        if status == 405: method="GET"; status, final, headers=fetch(source["url"],method,timeout)
    except (OSError, urllib.error.URLError) as error:
        return {"sourceId":source["id"],"requestedMethod":method,"outcome":"network_error","statusCode":None,"finalUrl":None,"contentType":None,"retryAfter":None,"errorClass":type(error).__name__}
    content=next((v.split(";",1)[0].strip().lower() for k,v in headers.items() if k.lower()=="content-type"),"")
    outcome="reachable" if 200<=status<300 and content in source["expectedContentTypes"] else "rate_limited" if status==429 else "unexpected_response"
    return {"sourceId":source["id"],"requestedMethod":method,"outcome":outcome,"statusCode":status,"finalUrl":final,"contentType":content or None,"retryAfter":next((v for k,v in headers.items() if k.lower()=="retry-after"),None),"errorClass":None}

def observe(config: dict[str, Any], timeout: float, fetch: Fetch = request_headers) -> dict[str, Any]:
    results=[probe(source,timeout,fetch) for source in config["sources"]]
    return {"schemaVersion":"meta-ads-official-canary-observation/v1","observedAt":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),"responseBodyStored":False,"artifactOnly":True,"sources":results,"summary":{outcome:sum(row["outcome"]==outcome for row in results) for outcome in ("reachable","rate_limited","unexpected_response","network_error")}}

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--config",type=Path,default=Path("config/meta_ads_official_canaries.json")); parser.add_argument("--output",type=Path,required=True); parser.add_argument("--timeout",type=float,default=20)
    args=parser.parse_args()
    try: report=observe(validate_config(json.loads(args.config.read_text(encoding="utf-8"))),args.timeout)
    except (OSError, ValueError, json.JSONDecodeError) as error: print(f"FAIL: {error}",file=sys.stderr); return 1
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print("PASS: artifact-only canary observation"); return 0
if __name__ == "__main__": raise SystemExit(main())
