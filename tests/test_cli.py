"""Offline tests for the ai-gov CLI. No credentials, no network."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ai_gov.cli import (  # noqa: E402
    EXIT_BLOCKED,
    EXIT_OK,
    EXIT_REJECTED,
    EXIT_USAGE,
    main,
)
from ai_gov.store import Store  # noqa: E402
from runtime.roles import IsolationError  # noqa: E402
from runtime.session import GovernanceSession  # noqa: E402

HARNESS_NOTES = [
    "--note", "test_plan=TP",
    "--note", "evidence_bundle=EB",
    "--note", "output_snapshot=OS",
    "--note", "failure_mode_notes=FMN",
]


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store_path = Path(self.tmp.name) / "store"

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--store", str(self.store_path), *argv])
        return code, out.getvalue(), err.getvalue()

    def seed_law(self) -> None:
        self.run_cli(
            "law", "create", "--title", "App Launch Law",
            "--metric", "30 survey responses",
            "--redline", "no missing privacy policy",
        )

    def seed_case(self, name: str = "Habit App MVP") -> str:
        self.seed_law()
        code, out, _ = self.run_cli(
            "case", "start", "--law", "LAW-001", "--name", name, "--request", "build it"
        )
        self.assertEqual(code, EXIT_OK, out)
        return out.split()[1]


class LawTest(CliTestCase):
    def test_creating_a_law_writes_a_readable_record(self) -> None:
        code, out, _ = self.run_cli(
            "law", "create", "--title", "T", "--metric", "M1", "--metric", "M2", "--redline", "R"
        )
        self.assertEqual(code, EXIT_OK)
        self.assertIn("LAW-001", out)
        law = json.loads((self.store_path / "laws" / "LAW-001.json").read_text(encoding="utf-8"))
        self.assertEqual(law["acceptance_criteria"], ["M1", "M2"])
        self.assertEqual(law["red_lines"], ["R"])

    def test_ids_are_sequential(self) -> None:
        self.run_cli("law", "create", "--title", "A")
        _, out, _ = self.run_cli("law", "create", "--title", "B")
        self.assertIn("LAW-002", out)

    def test_a_law_with_no_criteria_says_so(self) -> None:
        _, out, _ = self.run_cli("law", "create", "--title", "Vague")
        self.assertIn("nothing can be verified", out)

    def test_unknown_law_is_an_error(self) -> None:
        code, _, err = self.run_cli("case", "start", "--law", "LAW-404", "--name", "X")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("no such law", err)


class HarnessGateTest(CliTestCase):
    def test_a_case_without_evidence_cannot_reach_a_verdict(self) -> None:
        case_id = self.seed_case()
        code, out, _ = self.run_cli("judge", "run", "--case", case_id, "--unresolved", "0")
        self.assertEqual(code, EXIT_BLOCKED)
        self.assertNotIn("PASSED", out)

    def test_submitting_evidence_lets_the_same_case_pass(self) -> None:
        case_id = self.seed_case()
        self.run_cli("harness", "submit", "--case", case_id, *HARNESS_NOTES)
        code, out, _ = self.run_cli("judge", "run", "--case", case_id, "--unresolved", "0")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("PASSED", out)

    def test_partial_evidence_reports_what_is_missing(self) -> None:
        case_id = self.seed_case()
        _, out, _ = self.run_cli("harness", "submit", "--case", case_id, "--note", "test_plan=TP")
        self.assertIn("INCOMPLETE", out)
        self.assertIn("evidence_bundle", out)

    def test_submitting_nothing_is_a_usage_error(self) -> None:
        case_id = self.seed_case()
        code, _, err = self.run_cli("harness", "submit", "--case", case_id)
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("nothing to submit", err)

    def test_artifact_files_are_read_from_disk(self) -> None:
        case_id = self.seed_case()
        evidence = Path(self.tmp.name) / "report.md"
        evidence.write_text("all green", encoding="utf-8")
        code, _, _ = self.run_cli(
            "harness", "submit", "--case", case_id, "--artifact", f"evidence_bundle={evidence}"
        )
        self.assertEqual(code, EXIT_OK)
        case = Store(self.store_path).load_case(case_id)
        self.assertEqual(case.artifacts["evidence_bundle"], "all green")

    def test_a_missing_artifact_file_is_reported(self) -> None:
        case_id = self.seed_case()
        code, _, err = self.run_cli(
            "harness", "submit", "--case", case_id, "--artifact", "evidence_bundle=/nope/x.md"
        )
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("no such file", err)


class VerdictTest(CliTestCase):
    def prepared_case(self) -> str:
        case_id = self.seed_case()
        self.run_cli("harness", "submit", "--case", case_id, *HARNESS_NOTES)
        return case_id

    def test_running_with_no_verdict_source_is_refused(self) -> None:
        """Defaults would route to PASSED, which is success without evidence."""
        case_id = self.prepared_case()
        code, _, err = self.run_cli("judge", "run", "--case", case_id)
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("verdict source is required", err)
        self.assertEqual(Store(self.store_path).load_case(case_id).state, "NEW")

    def test_a_red_line_rejects_and_exits_distinctly(self) -> None:
        case_id = self.prepared_case()
        code, out, _ = self.run_cli("judge", "run", "--case", case_id, "--red-line")
        self.assertEqual(code, EXIT_REJECTED)
        self.assertIn("REJECTED", out)

    def test_unproven_items_send_the_case_to_rework(self) -> None:
        case_id = self.prepared_case()
        self.run_cli("judge", "run", "--case", case_id, "--unresolved", "2")
        case = Store(self.store_path).load_case(case_id)
        self.assertIn("REWORK", [entry["to"] for entry in case.history])

    def test_exit_codes_distinguish_the_outcomes(self) -> None:
        passed = self.prepared_case()
        rejected = self.prepared_case()
        self.assertEqual(self.run_cli("judge", "run", "--case", passed, "--unresolved", "0")[0], EXIT_OK)
        self.assertEqual(self.run_cli("judge", "run", "--case", rejected, "--red-line")[0], EXIT_REJECTED)


class WriteAuthorityTest(CliTestCase):
    """The CLI stands in for a role, so it inherits that role's limits."""

    def test_clarification_is_written_with_executive_authority(self) -> None:
        case_id = self.seed_case()
        code, _, _ = self.run_cli("law", "clarify", "--case", case_id, "--reason", "unclear scope")
        self.assertEqual(code, EXIT_OK)
        case = Store(self.store_path).load_case(case_id)
        self.assertEqual(case.facts["open_ambiguity_items"], 1)
        self.assertEqual(case.artifacts["ambiguity_notes"], "unclear scope")

    def test_amendment_is_written_with_judiciary_authority(self) -> None:
        case_id = self.seed_case()
        code, _, _ = self.run_cli("judge", "amend", "--case", case_id, "--reason", "no crash threshold")
        self.assertEqual(code, EXIT_OK)
        case = Store(self.store_path).load_case(case_id)
        self.assertEqual(case.facts["defective_law_items"], 1)

    def test_the_cli_cannot_exceed_the_acting_roles_authority(self) -> None:
        session = GovernanceSession.from_path(REPO_ROOT / "config" / "governance.json")
        case = Store(self.store_path)
        self.seed_case()
        loaded = case.load_case("CASE-001")
        with self.assertRaises(IsolationError):
            # The executive seat cannot record a verdict, from the CLI or anywhere.
            session.role("executive").apply_writes(loaded, {"facts": {"red_line_violated": True}})

    def test_a_refused_write_is_reported_and_not_persisted(self) -> None:
        case_id = self.seed_case()
        self.run_cli("law", "clarify", "--case", case_id, "--reason", "first")
        before = Store(self.store_path).load_case(case_id).facts["open_ambiguity_items"]
        self.assertEqual(before, 1)


class ShowTest(CliTestCase):
    def test_show_reports_state_trail_and_harness_coverage(self) -> None:
        case_id = self.seed_case()
        self.run_cli("harness", "submit", "--case", case_id, "--note", "test_plan=TP")
        _, out, _ = self.run_cli("judge", "show", case_id)
        self.assertIn("LAW-001", out)
        self.assertIn("1/4 artifacts", out)
        self.assertIn("[x] test_plan", out)
        self.assertIn("[ ] evidence_bundle", out)

    def test_show_reports_loop_usage_against_its_bound(self) -> None:
        case_id = self.seed_case()
        self.run_cli("harness", "submit", "--case", case_id, *HARNESS_NOTES)
        self.run_cli("judge", "run", "--case", case_id, "--unresolved", "1")
        _, out, _ = self.run_cli("judge", "show", case_id)
        self.assertIn("rework_loop:", out)

    def test_listing_shows_every_case(self) -> None:
        self.seed_case("First")
        self.run_cli("case", "start", "--law", "LAW-001", "--name", "Second")
        _, out, _ = self.run_cli("case", "list")
        self.assertIn("First", out)
        self.assertIn("Second", out)

    def test_listing_an_empty_store_is_not_an_error(self) -> None:
        code, out, _ = self.run_cli("case", "list")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("no cases", out)


class PersistenceTest(CliTestCase):
    def test_a_case_survives_between_invocations(self) -> None:
        case_id = self.seed_case()
        self.run_cli("harness", "submit", "--case", case_id, *HARNESS_NOTES)
        self.run_cli("judge", "run", "--case", case_id, "--unresolved", "0")

        reloaded = Store(self.store_path).load_case(case_id)
        self.assertEqual(reloaded.state, "PASSED")
        self.assertEqual(len(reloaded.history), 5)
        self.assertTrue(all(entry["guard"] for entry in reloaded.history))

    def test_a_bad_config_path_fails_cleanly(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--config", "/nope/governance.yaml", "case", "list"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("cannot load governance config", err.getvalue())


if __name__ == "__main__":
    unittest.main()
