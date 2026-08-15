#!/usr/bin/env python3
"""Install a validated approved report into the static Meta Ads UI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meta_ads_tracker_publication import load_json, validate_public_report, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("meta-ads-updates"))
    args = parser.parse_args()
    try:
        report = load_json(args.input)
        validate_public_report(report)
        write_json(args.output_dir / "latest.json", report)
        week_end = report["week"]["endDate"]
        write_json(args.output_dir / f"{week_end}.json", report)
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: built static Meta Ads index for {report['week']['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
