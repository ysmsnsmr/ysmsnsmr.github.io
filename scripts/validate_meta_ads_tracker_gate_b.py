#!/usr/bin/env python3
"""Validate the Gate B ledger contract without treating incomplete evidence as CI failure."""

from __future__ import annotations

import sys

from meta_ads_tracker_gate_b import main


if __name__ == "__main__":
    sys.argv.append("--validate-only")
    raise SystemExit(main())
