#!/usr/bin/env python3
"""Validate that the public Secondary β status matches the Gate B ledger."""

from __future__ import annotations

import sys

from meta_ads_tracker_secondary_beta_status import main


if __name__ == "__main__":
    sys.argv.append("--check")
    raise SystemExit(main())
