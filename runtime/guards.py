"""Guard implementations, one per `guard` name in `graph.edges`.

The config names a guard; this registry supplies its meaning. Keeping the two
apart is what lets the validator check that every declared edge has a guard
somebody actually wrote, instead of discovering it at run time.

Guards on the same source state must be mutually exclusive — otherwise routing
is nondeterministic and the flow is not reviewable. The fan-out guards below
are written to be exclusive by construction (each branch excludes the
conditions of the branches above it), and the executor still checks at run
time, because construction is an argument and the check is a fact.
"""

from __future__ import annotations

from typing import Any, Callable

from .case import Case

GuardFn = Callable[[Case, Any], bool]

GUARDS: dict[str, GuardFn] = {}


def guard(name: str) -> Callable[[GuardFn], GuardFn]:
    def register(fn: GuardFn) -> GuardFn:
        GUARDS[name] = fn
        return fn

    return register


# --- NEW / LEGISLATIVE: single outgoing edge each -------------------------


@guard("request_received")
def request_received(case: Case, ctx: Any) -> bool:
    return bool(case.fact("user_request", None))


@guard("law_published")
def law_published(case: Case, ctx: Any) -> bool:
    return bool(case.fact("law", None))


# --- EXECUTIVE fan-out ----------------------------------------------------


@guard("law_ambiguous")
def law_ambiguous(case: Case, ctx: Any) -> bool:
    return case.fact("open_ambiguity_items") > 0


@guard("all_required_artifacts_present")
def all_required_artifacts_present(case: Case, ctx: Any) -> bool:
    if case.fact("open_ambiguity_items") > 0:
        return False
    return all(name in case.artifacts for name in ctx.required_artifacts)


# --- HARNESS_SUBMITTED: single outgoing edge ------------------------------


@guard("harness_gate_satisfied")
def harness_gate_satisfied(case: Case, ctx: Any) -> bool:
    return all(name in case.artifacts for name in ctx.required_artifacts)


# --- JUDICIARY fan-out ----------------------------------------------------


@guard("red_line_violated")
def red_line_violated(case: Case, ctx: Any) -> bool:
    return bool(case.fact("red_line_violated", False))


@guard("law_defective")
def law_defective(case: Case, ctx: Any) -> bool:
    return not red_line_violated(case, ctx) and case.fact("defective_law_items") > 0


@guard("law_items_unproven")
def law_items_unproven(case: Case, ctx: Any) -> bool:
    if red_line_violated(case, ctx) or case.fact("defective_law_items") > 0:
        return False
    return case.fact("unresolved_law_items") > 0 or bool(case.invalid_artifacts)


@guard("all_law_items_proven")
def all_law_items_proven(case: Case, ctx: Any) -> bool:
    if red_line_violated(case, ctx) or case.fact("defective_law_items") > 0:
        return False
    return case.fact("unresolved_law_items") == 0 and not case.invalid_artifacts


# --- REWORK fan-out: the rework budget decides ----------------------------


@guard("rework_budget_remaining")
def rework_budget_remaining(case: Case, ctx: Any) -> bool:
    return case.iterations("rework_loop") <= ctx.loop_bound("rework_loop")


@guard("rework_budget_exhausted")
def rework_budget_exhausted(case: Case, ctx: Any) -> bool:
    return not rework_budget_remaining(case, ctx)


# --- Request states -------------------------------------------------------


@guard("amendment_accepted")
def amendment_accepted(case: Case, ctx: Any) -> bool:
    return True


@guard("clarification_needs_law_change")
def clarification_needs_law_change(case: Case, ctx: Any) -> bool:
    return bool(case.fact("clarification_requires_amendment", False))


@guard("clarification_resolved_in_place")
def clarification_resolved_in_place(case: Case, ctx: Any) -> bool:
    return not clarification_needs_law_change(case, ctx)
