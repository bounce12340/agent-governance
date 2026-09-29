"""Convergence rules: does the number a loop exists to reduce actually fall?

`convergence_metric` has been declared on every loop since the loop layer
landed, and until now nothing read it at run time. Stagnation detection
compared the per-iteration *artifact*, which answers a different question: it
notices when a role hands back the same paperwork, not when a role hands back
different paperwork that fixed nothing.

The rules here are deliberately about direction, not size. How fast a metric
should fall is a judgement about the work; whether it is allowed to grow while
a loop is supposedly fixing it is a governance question, and that is the one a
config can answer.
"""

from __future__ import annotations

from typing import Callable

RuleFn = Callable[[float, float], bool]

RULES: dict[str, RuleFn] = {}

DESCRIPTIONS = {
    "must_not_increase": "must not increase",
    "must_strictly_decrease": "must fall on every pass",
    "supervised_elsewhere": "is enforced outside loop accounting",
}


def rule(name: str) -> Callable[[RuleFn], RuleFn]:
    def register(fn: RuleFn) -> RuleFn:
        RULES[name] = fn
        return fn

    return register


@rule("must_not_increase")
def must_not_increase(previous: float, current: float) -> bool:
    """A flat pass is tolerated; the iteration bound already limits those.

    Growth is not: a loop whose metric climbs is making the case worse than
    when it entered.
    """
    return current <= previous


@rule("must_strictly_decrease")
def must_strictly_decrease(previous: float, current: float) -> bool:
    """For loops with so small a budget that a wasted pass is the whole story."""
    return current < previous


@rule("supervised_elsewhere")
def supervised_elsewhere(previous: float, current: float) -> bool:
    """The metric is real, but another layer owns it.

    `checkpoint_loop` counts missed checkpoints, which the supervisor derives
    from elapsed time rather than from anything loop accounting can see. Saying
    so is more honest than pretending the check runs here.
    """
    return True


def check(rule_name: str, values: list[float]) -> str | None:
    """Return why the metric failed to converge, or None if it is fine."""
    if len(values) < 2:
        return None
    fn = RULES.get(rule_name)
    if fn is None:
        return None
    previous, current = values[-2], values[-1]
    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return None
    if fn(previous, current):
        return None
    description = DESCRIPTIONS.get(rule_name, rule_name)
    return f"{description} but went {previous} -> {current}"
