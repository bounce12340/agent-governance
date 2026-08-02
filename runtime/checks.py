"""Artifact validity checks.

The harness gate has only ever asked whether evidence was *submitted*, never
whether it says anything. `gate_behavior.invalid_artifacts` has been in the
config since the first release with nothing able to reach it, because nothing
ever marked an artifact invalid.

These checks are deliberately mechanical. Deciding whether evidence actually
proves the law is the judiciary's job, and duplicating that here would be a
second judge with no isolation. What belongs here is the narrow question a
machine can answer without reading for meaning: is this artifact empty, is it a
placeholder, does a plan that must state a threshold state one?
"""

from __future__ import annotations

import re
from typing import Any, Callable

CheckFn = Callable[[Any], bool]

CHECKS: dict[str, CheckFn] = {}

# Values that occupy the slot without filling it.
PLACEHOLDERS = {
    "todo",
    "tbd",
    "tba",
    "n/a",
    "na",
    "none",
    "nil",
    "null",
    "pending",
    "fixme",
    "xxx",
    "-",
    "--",
    "?",
}


def check(name: str) -> Callable[[CheckFn], CheckFn]:
    def register(fn: CheckFn) -> CheckFn:
        CHECKS[name] = fn
        return fn

    return register


@check("non_empty")
def non_empty(value: Any) -> bool:
    return bool(str(value).strip())


@check("not_placeholder")
def not_placeholder(value: Any) -> bool:
    text = str(value).strip().lower().strip(".!。").strip()
    return bool(text) and text not in PLACEHOLDERS


@check("contains_a_number")
def contains_a_number(value: Any) -> bool:
    """A plan with no quantity in it states no threshold to test against.

    This is the repo's own rule applied mechanically: an acceptance criterion
    that cannot be counted cannot be verified.
    """
    return bool(re.search(r"\d", str(value)))


def failures(
    artifacts: dict[str, Any], artifact_checks: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Which submitted artifacts fail which checks.

    Absent artifacts are not reported here — a missing artifact is the gate's
    other verdict, and reporting it twice under two names would blur what the
    case is actually short of.
    """
    found: dict[str, list[str]] = {}
    for name, check_names in (artifact_checks or {}).items():
        if name not in artifacts:
            continue
        failed = [
            check_name
            for check_name in check_names or []
            if check_name in CHECKS and not CHECKS[check_name](artifacts[name])
        ]
        if failed:
            found[name] = failed
    return found
