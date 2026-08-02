"""Offline tests for artifact validity."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ai_gov.cli import EXIT_OK, main  # noqa: E402
from ai_gov.store import Store  # noqa: E402
from runtime.case import Case  # noqa: E402
from runtime.checks import CHECKS, failures  # noqa: E402
from runtime.executor import CaseRunner, RunStatus  # noqa: E402
from validate_governance import validate_config  # noqa: E402

CONFIG = json.loads((REPO_ROOT / "config" / "governance.json").read_text(encoding="utf-8"))
ARTIFACT_CHECKS = CONFIG["harness"]["artifact_checks"]
REQUIRED = CONFIG["harness"]["required_artifacts"]

GOOD = {
    "test_plan": "at least 30 responses, 5 interviews",
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
    artifacts = dict(GOOD)
    artifacts.update({"user_request": "req", "acceptance_criteria": "AC"})
    return Case("CASE-001", facts=base, artifacts=artifacts)


class CheckTest(unittest.TestCase):
    def test_blank_and_whitespace_are_empty(self) -> None:
        for value in ("", "   ", "\n\t "):
            with self.subTest(value=repr(value)):
                self.assertFalse(CHECKS["non_empty"](value))

    def test_real_content_is_not_empty(self) -> None:
        self.assertTrue(CHECKS["non_empty"]("a"))

    def test_placeholders_are_caught_in_their_usual_disguises(self) -> None:
        for value in ("TODO", "todo", " TBD ", "N/A", "n/a", "-", "?", "None", "pending."):
            with self.subTest(value=value):
                self.assertFalse(CHECKS["not_placeholder"](value))

    def test_a_sentence_containing_a_placeholder_word_still_passes(self) -> None:
        """The check rejects an artifact that *is* a placeholder, not one that mentions one."""
        self.assertTrue(CHECKS["not_placeholder"]("No blockers pending review of the export"))

    def test_a_plan_with_no_quantity_states_no_threshold(self) -> None:
        self.assertFalse(CHECKS["contains_a_number"]("we will test the app thoroughly"))
        self.assertTrue(CHECKS["contains_a_number"]("at least 30 responses"))


class FailureReportTest(unittest.TestCase):
    def test_good_evidence_reports_nothing(self) -> None:
        self.assertEqual(failures(GOOD, ARTIFACT_CHECKS), {})

    def test_each_failed_check_is_named(self) -> None:
        hollow = dict(GOOD, output_snapshot="   ", test_plan="tests exist")
        found = failures(hollow, ARTIFACT_CHECKS)
        self.assertEqual(found["test_plan"], ["contains_a_number"])
        self.assertEqual(found["output_snapshot"], ["non_empty", "not_placeholder"])

    def test_absent_artifacts_are_not_reported_as_invalid(self) -> None:
        """Missing is the gate's other verdict; reporting it twice blurs both."""
        partial = {"test_plan": GOOD["test_plan"]}
        self.assertEqual(failures(partial, ARTIFACT_CHECKS), {})


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CaseRunner(copy.deepcopy(CONFIG))

    def test_hollow_evidence_reaches_rework_not_passed(self) -> None:
        """Before this layer, a clean verdict on hollow evidence went straight to PASSED."""
        case = clean_case()
        case.artifacts["test_plan"] = "we will test it"
        result = self.runner.run(case)
        self.assertNotEqual(case.state, "PASSED")
        self.assertIn("REWORK", [entry["to"] for entry in case.history])
        self.assertIn("test_plan", case.invalid_artifacts)
        self.assertEqual(result.status, RunStatus.BLOCKED)

    def test_sound_evidence_still_passes(self) -> None:
        case = clean_case()
        self.runner.run(case)
        self.assertEqual(case.state, "PASSED")
        self.assertEqual(case.invalid_artifacts, set())

    def test_missing_evidence_is_still_a_separate_verdict(self) -> None:
        case = clean_case()
        case.state = "HARNESS_SUBMITTED"
        case.artifacts.pop("failure_mode_notes")
        result = self.runner.step(case)
        self.assertEqual(result.status, RunStatus.BLOCKED)
        self.assertIn("INCOMPLETE", result.note)
        self.assertEqual(case.invalid_artifacts, set())

    def test_an_incomplete_bundle_never_leaves_the_executive(self) -> None:
        case = clean_case()
        case.artifacts.pop("failure_mode_notes")
        result = self.runner.run(case)
        self.assertEqual(result.status, RunStatus.BLOCKED)
        self.assertEqual(case.state, "EXECUTIVE")

    def test_repairing_an_artifact_clears_its_mark(self) -> None:
        case = clean_case()
        case.state = "HARNESS_SUBMITTED"
        case.artifacts["evidence_bundle"] = "TBD"
        self.runner.gate_check(case)
        self.assertEqual(case.invalid_artifacts, {"evidence_bundle"})

        case.artifacts["evidence_bundle"] = "export attached"
        self.runner.gate_check(case)
        self.assertEqual(case.invalid_artifacts, set())
        self.assertEqual(case.artifact_failures, {})

    def test_the_reason_is_recorded_not_just_the_fact(self) -> None:
        case = clean_case()
        case.state = "HARNESS_SUBMITTED"
        case.artifacts["test_plan"] = "TODO"
        self.runner.gate_check(case)
        self.assertEqual(
            case.artifact_failures["test_plan"], ["not_placeholder", "contains_a_number"]
        )


class ConfigContractTest(unittest.TestCase):
    def mutated(self, mutate) -> list[str]:
        doc = copy.deepcopy(CONFIG)
        mutate(doc)
        return validate_config(doc)

    def test_check_registry_matches_the_validator(self) -> None:
        from validate_governance import KNOWN_ARTIFACT_CHECKS

        self.assertEqual(set(CHECKS), KNOWN_ARTIFACT_CHECKS)

    def test_every_required_artifact_must_declare_checks(self) -> None:
        errors = self.mutated(lambda d: d["harness"]["artifact_checks"].pop("evidence_bundle"))
        self.assertTrue(any("artifact_checks missing entries" in e for e in errors), errors)

    def test_an_artifact_with_no_checks_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["harness"]["artifact_checks"].__setitem__("test_plan", [])
        )
        self.assertTrue(any("must not be empty" in e for e in errors), errors)

    def test_an_unimplemented_check_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["harness"]["artifact_checks"]["test_plan"].append("looks_convincing")
        )
        self.assertTrue(any("no implementation for" in e for e in errors), errors)


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store_path = Path(self.tmp.name) / "store"
        self.run_cli("law", "create", "--title", "L", "--metric", "30 responses")
        self.run_cli("case", "start", "--law", "LAW-001", "--name", "N", "--request", "build it")

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--store", str(self.store_path), *argv])
        return code, out.getvalue(), err.getvalue()

    def submit(self, **notes) -> tuple[int, str, str]:
        argv = ["harness", "submit", "--case", "CASE-001"]
        for name, value in notes.items():
            argv += ["--note", f"{name}={value}"]
        return self.run_cli(*argv)

    def test_submit_reports_hollow_evidence_without_refusing_it(self) -> None:
        """The record should say the executive submitted it, not pretend it did not."""
        code, out, _ = self.submit(test_plan="tests exist", evidence_bundle="TODO")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("test_plan fails contains_a_number", out)
        self.assertIn("evidence_bundle fails not_placeholder", out)

        case = Store(self.store_path).load_case("CASE-001")
        self.assertEqual(case.artifacts["evidence_bundle"], "TODO")

    def test_show_marks_invalid_artifacts_and_why(self) -> None:
        self.submit(**GOOD)
        self.submit(test_plan="no numbers here")
        self.run_cli("judge", "run", "--case", "CASE-001", "--unresolved", "0")
        _, out, _ = self.run_cli("judge", "show", "CASE-001")
        self.assertIn("[!] test_plan — fails contains_a_number", out)
        self.assertIn("[x] evidence_bundle", out)

    def test_a_clean_verdict_on_hollow_evidence_does_not_pass(self) -> None:
        self.submit(**dict(GOOD, output_snapshot="   "))
        code, out, _ = self.run_cli("judge", "run", "--case", "CASE-001", "--unresolved", "0")
        self.assertNotIn("PASSED", out)
        self.assertNotEqual(code, EXIT_OK)

    def test_repaired_evidence_lets_the_same_case_finish(self) -> None:
        self.submit(**dict(GOOD, test_plan="tests exist"))
        self.run_cli("judge", "run", "--case", "CASE-001", "--unresolved", "0")
        self.submit(test_plan="at least 30 responses", rework_diff_note="rewrote the plan")
        code, out, _ = self.run_cli("judge", "run", "--case", "CASE-001", "--unresolved", "0")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("PASSED", out)


if __name__ == "__main__":
    unittest.main()
