"""Offline tests for convergence checking: does the metric actually fall?"""

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
from runtime.convergence import RULES, check  # noqa: E402
from runtime.executor import CaseRunner, RunStatus  # noqa: E402
from validate_governance import validate_config  # noqa: E402

CONFIG = json.loads((REPO_ROOT / "config" / "governance.json").read_text(encoding="utf-8"))
LOOPS = CONFIG["loops"]

GOOD_EVIDENCE = {
    "test_plan": "at least 30 responses",
    "evidence_bundle": "survey export attached",
    "output_snapshot": "screenshots of the core flow",
    "failure_mode_notes": "crash on empty state, documented",
}


def clean_case(**facts) -> Case:
    base = {
        "user_request": "build it",
        "law": "LAW-001",
        "open_ambiguity_items": 0,
        "unresolved_law_items": 0,
        "defective_law_items": 0,
        "red_line_violated": False,
    }
    base.update(facts)
    artifacts = dict(GOOD_EVIDENCE)
    artifacts.update({"user_request": "req", "acceptance_criteria": "AC"})
    return Case("CASE-001", facts=base, artifacts=artifacts)


class RuleTest(unittest.TestCase):
    def test_must_not_increase_tolerates_flat_but_refuses_growth(self) -> None:
        rule = RULES["must_not_increase"]
        self.assertTrue(rule(3, 2))
        self.assertTrue(rule(3, 3))
        self.assertFalse(rule(3, 4))

    def test_must_strictly_decrease_refuses_a_wasted_pass(self) -> None:
        rule = RULES["must_strictly_decrease"]
        self.assertTrue(rule(3, 2))
        self.assertFalse(rule(3, 3))
        self.assertFalse(rule(3, 4))

    def test_supervised_elsewhere_defers_rather_than_pretending(self) -> None:
        rule = RULES["supervised_elsewhere"]
        self.assertTrue(rule(0, 99))

    def test_a_single_reading_cannot_fail(self) -> None:
        self.assertIsNone(check("must_strictly_decrease", [5]))
        self.assertIsNone(check("must_strictly_decrease", []))

    def test_non_numeric_readings_are_skipped_not_guessed(self) -> None:
        self.assertIsNone(check("must_not_increase", ["a", "b"]))

    def test_the_reason_names_the_direction_it_went(self) -> None:
        reason = check("must_not_increase", [2, 5])
        self.assertIn("2", reason)
        self.assertIn("5", reason)


class LoopConvergenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CaseRunner(copy.deepcopy(CONFIG))

    def drive(self, state: str, artifact: str, metric: str, readings: list[int]):
        """Enter a loop repeatedly, forcing the metric to a chosen value each pass."""
        case = clean_case(**{metric: readings[0]})
        case.state = state
        result = None
        for index, value in enumerate(readings):
            case.facts[metric] = value
            case.artifacts[artifact] = f"fresh-{index}"
            result = self.runner.step(case)
            if result.status is not RunStatus.MOVED:
                break
            # Walk back to the loop's entry state for the next pass.
            for _ in range(6):
                if case.state == state:
                    break
                stepped = self.runner.step(case)
                if stepped.status is not RunStatus.MOVED:
                    result = stepped
                    break
            if case.state != state:
                break
        return case, result

    def test_a_rising_metric_ends_the_rework_loop(self) -> None:
        case, result = self.drive(
            "JUDICIARY", "rework_diff_note", "unresolved_law_items", [2, 5]
        )
        self.assertEqual(result.status, RunStatus.ESCALATED)
        self.assertIn("did not converge", result.note)
        self.assertIn("unresolved_law_items", result.note)

    def test_a_falling_metric_keeps_the_rework_loop_running(self) -> None:
        case, result = self.drive(
            "JUDICIARY", "rework_diff_note", "unresolved_law_items", [3, 2]
        )
        self.assertNotEqual(result.status, RunStatus.ESCALATED)
        self.assertEqual(case.loop_metrics["rework_loop"], [3, 2])

    def test_a_flat_metric_is_allowed_where_the_rule_permits_it(self) -> None:
        """rework declares must_not_increase, so the bound handles flat passes."""
        case, result = self.drive(
            "JUDICIARY", "rework_diff_note", "unresolved_law_items", [2, 2]
        )
        self.assertNotIn("did not converge", result.note or "")

    def test_a_flat_metric_ends_a_loop_that_demands_a_fall(self) -> None:
        case, result = self.drive(
            "JUDICIARY", "amendment_reason", "defective_law_items", [1, 1]
        )
        self.assertEqual(result.status, RunStatus.ESCALATED)
        self.assertIn("did not converge", result.note)

    def test_readings_are_recorded_for_the_audit_trail(self) -> None:
        case, _ = self.drive("JUDICIARY", "rework_diff_note", "unresolved_law_items", [4, 9])
        self.assertEqual(case.loop_metrics["rework_loop"], [4, 9])
        self.assertIn("escalation", case.history[-1])

    def test_readings_survive_serialisation(self) -> None:
        case, _ = self.drive("JUDICIARY", "rework_diff_note", "unresolved_law_items", [4, 9])
        restored = Case.from_dict(json.loads(json.dumps(case.to_dict())))
        self.assertEqual(restored.loop_metrics, case.loop_metrics)


class ConfigContractTest(unittest.TestCase):
    def mutated(self, mutate) -> list[str]:
        doc = copy.deepcopy(CONFIG)
        mutate(doc)
        return validate_config(doc)

    def test_shipped_config_passes(self) -> None:
        self.assertEqual(validate_config(copy.deepcopy(CONFIG)), [])

    def test_rule_registry_matches_the_validator(self) -> None:
        from validate_governance import KNOWN_CONVERGENCE_RULES

        self.assertEqual(set(RULES), KNOWN_CONVERGENCE_RULES)

    def test_every_loop_declares_a_rule(self) -> None:
        for name, loop in LOOPS.items():
            with self.subTest(loop=name):
                self.assertIn(loop["convergence_rule"], RULES)

    def test_an_unimplemented_rule_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["loops"]["rework_loop"].__setitem__("convergence_rule", "vibes")
        )
        self.assertTrue(any("convergence_rule must be one of" in e for e in errors), errors)

    def test_a_missing_rule_is_rejected(self) -> None:
        errors = self.mutated(lambda d: d["loops"]["rework_loop"].pop("convergence_rule"))
        self.assertTrue(any("convergence_rule" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
