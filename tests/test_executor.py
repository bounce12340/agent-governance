"""Offline tests for the state machine executor."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from runtime.case import Case  # noqa: E402
from runtime.executor import (  # noqa: E402
    CaseRunner,
    ExecutionError,
    NondeterministicRouting,
    RunStatus,
)
from runtime.guards import GUARDS  # noqa: E402

CONFIG = json.loads((REPO_ROOT / "config" / "governance.json").read_text(encoding="utf-8"))
REQUIRED_ARTIFACTS = CONFIG["harness"]["required_artifacts"]

# Edges carry their own evidence requirements on top of the harness bundle.
# Deriving the fixture from the config keeps it correct when an edge changes.
EDGE_EVIDENCE = {
    edge["required_evidence"]
    for targets in CONFIG["graph"]["edges"].values()
    for edge in targets.values()
}
ALL_EVIDENCE = sorted(set(REQUIRED_ARTIFACTS) | EDGE_EVIDENCE)


def full_evidence(**extra) -> dict[str, str]:
    bundle = {name: f"{name}-v1" for name in ALL_EVIDENCE}
    bundle.update(extra)
    return bundle


def clean_case(**facts) -> Case:
    base = {
        "user_request": "build the thing",
        "law": "LAW-001",
        "open_ambiguity_items": 0,
        "unresolved_law_items": 0,
        "defective_law_items": 0,
        "red_line_violated": False,
    }
    base.update(facts)
    return Case(case_id="CASE-001", facts=base, artifacts=full_evidence())


class HappyPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CaseRunner(copy.deepcopy(CONFIG))

    def test_a_clean_case_reaches_passed(self) -> None:
        case = clean_case()
        result = self.runner.run(case)
        self.assertEqual(result.status, RunStatus.TERMINAL)
        self.assertEqual(case.state, "PASSED")
        self.assertEqual(
            case.trail(),
            "NEW -> LEGISLATIVE -> EXECUTIVE -> HARNESS_SUBMITTED -> JUDICIARY -> PASSED",
        )

    def test_history_records_the_guard_and_evidence_for_every_hop(self) -> None:
        case = clean_case()
        self.runner.run(case)
        for entry in case.history:
            self.assertTrue(entry["guard"], entry)
            self.assertTrue(entry["evidence"], entry)


class HarnessGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CaseRunner(copy.deepcopy(CONFIG))

    def test_missing_evidence_never_reaches_judiciary(self) -> None:
        case = clean_case()
        case.artifacts.pop("failure_mode_notes")
        result = self.runner.run(case)
        self.assertEqual(result.status, RunStatus.BLOCKED)
        self.assertNotIn(case.state, {"JUDICIARY", "PASSED"})

    def test_gate_verdict_comes_from_the_config(self) -> None:
        case = clean_case()
        case.state = "HARNESS_SUBMITTED"
        case.artifacts.pop("test_plan")
        result = self.runner.step(case)
        self.assertEqual(result.status, RunStatus.BLOCKED)
        self.assertTrue(result.note.startswith(CONFIG["harness"]["gate_behavior"]["missing_artifacts"]))
        self.assertIn("test_plan", result.note)

    def test_invalid_evidence_routes_to_rework_not_passed(self) -> None:
        case = clean_case()
        case.invalid_artifacts.add("output_snapshot")
        case.state = "JUDICIARY"
        result = self.runner.step(case)
        self.assertEqual(result.target, "REWORK")


class VerdictRoutingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CaseRunner(copy.deepcopy(CONFIG))

    def route_from_judiciary(self, **facts) -> str | None:
        case = clean_case(**facts)
        case.state = "JUDICIARY"
        return self.runner.step(case).target

    def test_red_line_rejects(self) -> None:
        self.assertEqual(self.route_from_judiciary(red_line_violated=True), "REJECTED")

    def test_defective_law_requests_amendment(self) -> None:
        self.assertEqual(
            self.route_from_judiciary(defective_law_items=1), "LAW_AMENDMENT_REQUEST"
        )

    def test_unproven_items_return_rework(self) -> None:
        self.assertEqual(self.route_from_judiciary(unresolved_law_items=2), "REWORK")

    def test_red_line_outranks_every_other_verdict(self) -> None:
        target = self.route_from_judiciary(
            red_line_violated=True, defective_law_items=3, unresolved_law_items=5
        )
        self.assertEqual(target, "REJECTED")


class MutualExclusionTest(unittest.TestCase):
    """Guard exclusion used to be a documented convention. It is now checked."""

    def setUp(self) -> None:
        self.runner = CaseRunner(copy.deepcopy(CONFIG))

    def test_every_fan_out_has_at_most_one_open_door(self) -> None:
        fan_outs = {
            source: targets
            for source, targets in self.runner.edges.items()
            if len(targets) > 1
        }
        self.assertTrue(fan_outs, "expected the graph to contain fan-outs")

        combinations = [
            {},
            {"red_line_violated": True},
            {"defective_law_items": 1},
            {"unresolved_law_items": 3},
            {"open_ambiguity_items": 2},
            {"clarification_requires_amendment": True},
            {"defective_law_items": 1, "unresolved_law_items": 3},
            {"red_line_violated": True, "defective_law_items": 2},
        ]
        for source in fan_outs:
            for facts in combinations:
                for iterations in (0, 99):
                    case = clean_case(**facts)
                    case.state = source
                    case.loop_iterations["rework_loop"] = iterations
                    open_doors = [
                        target
                        for target, edge in fan_outs[source].items()
                        if GUARDS[edge["guard"]](case, self.runner)
                    ]
                    self.assertLessEqual(
                        len(open_doors),
                        1,
                        f"{source} opened {open_doors} for facts={facts} iterations={iterations}",
                    )

    def test_two_open_guards_are_refused_rather_than_resolved(self) -> None:
        doc = copy.deepcopy(CONFIG)
        # Point both REWORK edges at a guard that is always true.
        doc["graph"]["edges"]["REWORK"]["EXECUTIVE"]["guard"] = "amendment_accepted"
        doc["graph"]["edges"]["REWORK"]["REJECTED"]["guard"] = "amendment_accepted"
        runner = CaseRunner(doc)
        case = clean_case()
        case.state = "REWORK"
        with self.assertRaises(NondeterministicRouting):
            runner.step(case)

    def test_an_unimplemented_guard_is_refused(self) -> None:
        doc = copy.deepcopy(CONFIG)
        doc["graph"]["edges"]["NEW"]["LEGISLATIVE"]["guard"] = "vibes"
        with self.assertRaises(ExecutionError):
            CaseRunner(doc).step(clean_case())


class LoopBoundTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CaseRunner(copy.deepcopy(CONFIG))
        self.bound = CONFIG["loops"]["rework_loop"]["max_iterations"]

    def test_rework_is_capped_at_the_declared_bound(self) -> None:
        case = clean_case(unresolved_law_items=1)
        for _ in range(60):
            result = self.runner.step(case)
            if result.status in {RunStatus.TERMINAL, RunStatus.BLOCKED, RunStatus.ESCALATED}:
                break
            if case.state == "EXECUTIVE":
                # Fresh evidence each pass, so the cap is what stops the loop
                # rather than the stagnation rule.
                case.artifacts = full_evidence(
                    rework_diff_note=f"attempt-{case.iterations('rework_loop')}"
                )
        self.assertEqual(case.state, "REJECTED")
        reworks = [h for h in case.history if h["from"] == "REWORK" and h["to"] == "EXECUTIVE"]
        self.assertEqual(len(reworks), self.bound)

    def test_iteration_counter_tracks_loop_entries(self) -> None:
        case = clean_case(unresolved_law_items=1)
        case.state = "JUDICIARY"
        case.artifacts["rework_diff_note"] = "first"
        self.runner.step(case)
        self.assertEqual(case.iterations("rework_loop"), 1)
        self.assertEqual(case.state, "REWORK")


class LoopBudgetTest(unittest.TestCase):
    """Fresh evidence every pass defeats stagnation detection.

    That is precisely when the declared bound has to do the work, so each loop
    is driven with a changing artifact to prove counting alone stops it.
    """

    def setUp(self) -> None:
        self.runner = CaseRunner(copy.deepcopy(CONFIG))

    def drive(self, state: str, artifact: str, **facts) -> tuple[Case, object]:
        case = clean_case(**facts)
        case.state = state
        result = None
        for index in range(20):
            case.artifacts[artifact] = f"fresh-{index}"
            result = self.runner.step(case)
            if result.status is not RunStatus.MOVED:
                break
        return case, result

    def test_clarification_loop_stops_at_its_declared_bound(self) -> None:
        bound = CONFIG["loops"]["clarification_loop"]["max_iterations"]
        case, result = self.drive("EXECUTIVE", "ambiguity_notes", open_ambiguity_items=1)
        self.assertEqual(result.status, RunStatus.ESCALATED)
        self.assertEqual(case.iterations("clarification_loop"), bound + 1)
        self.assertIn(f"exceeded its bound of {bound}", result.note)

    def test_amendment_loop_stops_at_its_declared_bound(self) -> None:
        bound = CONFIG["loops"]["amendment_loop"]["max_iterations"]
        case, result = self.drive("JUDICIARY", "amendment_reason", defective_law_items=1)
        self.assertEqual(result.status, RunStatus.ESCALATED)
        self.assertEqual(case.iterations("amendment_loop"), bound + 1)

    def test_no_loop_outruns_its_bound(self) -> None:
        """A sweep, so a loop added later cannot quietly go unbounded."""
        drives = {
            "clarification_loop": ("EXECUTIVE", "ambiguity_notes", {"open_ambiguity_items": 1}),
            "amendment_loop": ("JUDICIARY", "amendment_reason", {"defective_law_items": 1}),
            "rework_loop": ("JUDICIARY", "rework_diff_note", {"unresolved_law_items": 1}),
        }
        graph_loops = {
            name for name, loop in CONFIG["loops"].items() if loop.get("scope") == "graph"
        }
        self.assertEqual(set(drives), graph_loops, "a declared graph loop has no drive here")

        for name, (state, artifact, facts) in drives.items():
            with self.subTest(loop=name):
                case, result = self.drive(state, artifact, **facts)
                bound = CONFIG["loops"][name]["max_iterations"]
                self.assertLessEqual(case.iterations(name), bound + 1)
                self.assertIn(
                    result.status, {RunStatus.ESCALATED, RunStatus.TERMINAL, RunStatus.BLOCKED}
                )

    def test_the_graph_routes_the_overflow_when_it_can(self) -> None:
        """rework's escalation target has a declared edge, so the guards take it."""
        case, _ = self.drive("JUDICIARY", "rework_diff_note", unresolved_law_items=1)
        self.assertEqual(case.state, "REJECTED")
        # Through REWORK on a declared guard, not jumped there by the loop layer.
        self.assertEqual([h["to"] for h in case.history][-2:], ["REWORK", "REJECTED"])
        self.assertEqual(case.history[-1]["guard"], "rework_budget_exhausted")
        self.assertNotIn("escalation", case.history[-1])

    def test_an_escalation_hop_records_why_not_just_which_guard(self) -> None:
        case = clean_case(open_ambiguity_items=1)
        case.state = "EXECUTIVE"
        case.artifacts["ambiguity_notes"] = "same question"
        self.runner.step(case)
        case.state = "EXECUTIVE"
        self.runner.step(case)
        self.assertIn("escalation", case.history[-1])
        self.assertIn("stagnated", case.history[-1]["escalation"])


class StagnationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CaseRunner(copy.deepcopy(CONFIG))

    def enter_rework(self, case: Case) -> None:
        case.state = "JUDICIARY"
        self.runner.step(case)

    def test_identical_evidence_twice_escalates_before_the_budget_runs_out(self) -> None:
        case = clean_case(unresolved_law_items=1)
        case.artifacts["rework_diff_note"] = "same-every-time"
        self.enter_rework(case)
        case.state = "JUDICIARY"
        result = self.runner.step(case)

        self.assertEqual(result.status, RunStatus.ESCALATED)
        self.assertIn("rework_loop stagnated", result.note)
        self.assertEqual(case.state, "REJECTED")
        self.assertLess(case.iterations("rework_loop"), CONFIG["constitution"]["max_rework_count"] + 1)

    def test_changing_evidence_does_not_count_as_stagnation(self) -> None:
        case = clean_case(unresolved_law_items=1)
        case.artifacts["rework_diff_note"] = "attempt-1"
        self.enter_rework(case)
        case.artifacts["rework_diff_note"] = "attempt-2"
        case.state = "JUDICIARY"
        result = self.runner.step(case)
        self.assertEqual(result.status, RunStatus.MOVED)

    def test_escalation_does_not_teleport_across_the_graph(self) -> None:
        """clarification_loop escalates to a state with no edge from here."""
        case = clean_case(open_ambiguity_items=1)
        case.artifacts["ambiguity_notes"] = "same-question"
        case.state = "EXECUTIVE"
        self.runner.step(case)
        case.state = "EXECUTIVE"
        result = self.runner.step(case)

        self.assertEqual(result.status, RunStatus.ESCALATED)
        self.assertIn("no legal edge", result.note)
        target = CONFIG["loops"]["clarification_loop"]["escalation_target"]
        self.assertNotIn(target, self.runner.edges.get("LAW_CLARIFICATION_REQUEST", {}))


class RegistryTest(unittest.TestCase):
    def test_guard_registry_matches_the_validator(self) -> None:
        from validate_governance import KNOWN_GUARDS

        self.assertEqual(set(GUARDS), KNOWN_GUARDS)

    def test_every_declared_edge_has_an_implemented_guard(self) -> None:
        for source, targets in (CONFIG["graph"]["edges"]).items():
            for target, edge in targets.items():
                self.assertIn(edge["guard"], GUARDS, f"{source} -> {target}")


if __name__ == "__main__":
    unittest.main()
