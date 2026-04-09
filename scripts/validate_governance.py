#!/usr/bin/env python3
"""Validate the governance config and core governance artifacts.

This is a lightweight, dependency-free guardrail for the repo's governance
model. It checks that the constitution layer, harness gate, reverse feedback,
and rework cap are all present in the config file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED_MARKERS = [
    "require_harness_before_judgment:",
    "max_rework_count:",
    "allow_judiciary_law_amendment_request:",
    "allow_executive_clarification_request:",
    "role_isolation:",
    "workflow:",
    "harness:",
    "HARNESS_SUBMITTED",
    "LAW_CLARIFICATION_REQUEST",
    "LAW_AMENDMENT_REQUEST",
    "REWORK",
]


def validate_text(text: str) -> list[str]:
    errors: list[str] = []
    for marker in REQUIRED_MARKERS:
        if marker not in text:
            errors.append(f"missing marker: {marker}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate governance config")
    parser.add_argument(
        "path",
        nargs="?",
        default="config/governance.yaml",
        help="Path to governance config (default: config/governance.yaml)",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    errors = validate_text(text)

    if errors:
        print(f"FAIL: {path}")
        for error in errors:
            print(f"- {error}")
        return 2

    print(f"PASS: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
