"""Offline tests for long-task supervision. The clock is always an argument."""

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

from ai_gov.cli import EXIT_BLOCKED, EXIT_ESCALATED, EXIT_OK, EXIT_USAGE, main  # noqa: E402
from ai_gov.store import Store  # noqa: E402
from runtime.case import Case  # noqa: E402
from runtime.roles import IsolationError  # noqa: E402
from runtime.session import GovernanceSession  # noqa: E402
from runtime.supervision import (  # noqa: E402
    CheckpointStatus,
    CheckpointSupervisor,
    SupervisionError,
)
from validate_governance import validate_config  # noqa: E402

CONFIG = json.loads((REPO_ROOT / "config" / "governance.json").read_text(encoding="utf-8"))
LONG_TASK = CONFIG["long_task"]
INTERVAL = LONG_TASK["checkpoint_interval_minutes"] * 60
GRACE = LONG_TASK["checkpoint_grace_minutes"] * 60
DEADLINE = INTERVAL + GRACE

SUMMARY = {"completed": "auth", "blocked": "none", "next_step": "storage", "eta": "2d"}


def started_case(supervisor: CheckpointSupervisor) -> Case:
    case = Case("CASE-001")
    supervisor.start(case, now=0)
    return case


class ClockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.supervisor = CheckpointSupervisor(copy.deepcopy(CONFIG))
        self.case = started_case(self.supervisor)

    def test_nothing_is_late_before_the_clock_starts(self) -> None:
        fresh = Case("CASE-002")
        result = self.supervisor.review(fresh, now=10**9)
        self.assertEqual(result.status, CheckpointStatus.HEALTHY)

    def test_on_time_right_up_to_the_deadline(self) -> None:
        self.assertEqual(self.supervisor.deadline(self.case), DEADLINE)
        for stamp in (0, INTERVAL, DEADLINE - 1, DEADLINE):
            with self.subTest(stamp=stamp):
                self.assertEqual(
                    self.supervisor.review(self.case, now=stamp).status,
                    CheckpointStatus.HEALTHY,
                )

    def test_one_second_past_the_deadline_is_one_missed_checkpoint(self) -> None:
        result = self.supervisor.review(self.case, now=DEADLINE + 1)
        self.assertEqual(result.status, CheckpointStatus.OVERDUE)
        self.assertEqual(result.missed, 1)

    def test_each_further_interval_adds_one_miss(self) -> None:
        for extra, expected in ((1, 1), (INTERVAL, 2), (INTERVAL * 2, 3)):
            with self.subTest(extra=extra):
                self.assertEqual(
                    self.supervisor.review(self.case, now=DEADLINE + extra).missed, expected
                )

    def test_reviewing_twice_does_not_inflate_the_count(self) -> None:
        """The count is derived from elapsed time, never incremented."""
        first = self.supervisor.review(self.case, now=DEADLINE + INTERVAL)
        second = self.supervisor.review(self.case, now=DEADLINE + INTERVAL)
        self.assertEqual(first.missed, second.missed)
        self.assertEqual(self.case.missed_checkpoints, second.missed)

    def test_passing_the_limit_escalates(self) -> None:
        over = DEADLINE + INTERVAL * LONG_TASK["max_missed_checkpoints"]
        result = self.supervisor.review(self.case, now=over)
        self.assertEqual(result.status, CheckpointStatus.ESCALATED)
        self.assertIn(LONG_TASK["escalation_on_miss"], result.note)

    def test_supervision_can_be_switched_off_in_config(self) -> None:
        doc = copy.deepcopy(CONFIG)
        doc["long_task"]["enabled"] = False
        off = CheckpointSupervisor(doc)
        self.assertEqual(off.review(self.case, now=10**9).status, CheckpointStatus.DISABLED)


class ProgressSummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.supervisor = CheckpointSupervisor(copy.deepcopy(CONFIG))
        self.case = started_case(self.supervisor)

    def test_a_report_missing_a_field_is_not_a_report(self) -> None:
        for field in LONG_TASK["require_progress_summary"]:
            with self.subTest(field=field):
                partial = dict(SUMMARY, **{field: ""})
                with self.assertRaises(SupervisionError) as caught:
                    self.supervisor.record(Case("CASE-X"), partial, now=0)
                self.assertIn(field, str(caught.exception))

    def test_a_valid_checkpoint_resets_the_clock_and_the_count(self) -> None:
        self.supervisor.review(self.case, now=DEADLINE + 1)
        self.assertEqual(self.case.missed_checkpoints, 1)

        self.supervisor.record(self.case, SUMMARY, now=DEADLINE + 1)
        self.assertEqual(self.case.missed_checkpoints, 0)
        self.assertEqual(self.case.last_checkpoint_at, DEADLINE + 1)
        self.assertEqual(
            self.supervisor.review(self.case, now=DEADLINE + 2).status, CheckpointStatus.HEALTHY
        )

    def test_repeating_the_previous_report_is_stagnation(self) -> None:
        self.supervisor.record(self.case, SUMMARY, now=100)
        result = self.supervisor.record(self.case, dict(SUMMARY), now=200)
        self.assertEqual(result.status, CheckpointStatus.STAGNATED)
        self.assertIn("identical_progress_summary_twice", result.note)

    def test_a_changed_report_is_not_stagnation(self) -> None:
        self.supervisor.record(self.case, SUMMARY, now=100)
        moved_on = dict(SUMMARY, completed="auth and storage")
        self.assertEqual(
            self.supervisor.record(self.case, moved_on, now=200).status, CheckpointStatus.HEALTHY
        )

    def test_only_the_declared_fields_are_recorded(self) -> None:
        self.supervisor.record(self.case, dict(SUMMARY, mood="great"), now=100)
        recorded = self.case.checkpoints[-1]
        self.assertNotIn("mood", recorded)
        self.assertEqual(recorded["completed"], "auth")


class EscalationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.supervisor = CheckpointSupervisor(copy.deepcopy(CONFIG))
        self.session = GovernanceSession(copy.deepcopy(CONFIG))
        self.case = started_case(self.supervisor)

    def test_escalation_uses_executive_authority_and_no_more(self) -> None:
        written = self.supervisor.escalate(self.case, self.session, "went quiet")
        self.assertEqual(sorted(written), ["ambiguity_notes", "open_ambiguity_items"])
        self.assertEqual(self.case.facts["open_ambiguity_items"], 1)

    def test_supervision_cannot_write_a_verdict(self) -> None:
        """Escalation is the executive raising its hand, not a judgment."""
        with self.assertRaises(IsolationError):
            self.session.role("executive").apply_writes(
                self.case, {"facts": {"red_line_violated": True}}
            )

    def test_escalation_does_not_move_the_case_itself(self) -> None:
        before = self.case.state
        self.supervisor.escalate(self.case, self.session, "went quiet")
        self.assertEqual(self.case.state, before)
        self.assertEqual(self.case.history, [])


class ConfigContractTest(unittest.TestCase):
    def mutated(self, mutate) -> list[str]:
        doc = copy.deepcopy(CONFIG)
        mutate(doc)
        return validate_config(doc)

    def test_the_two_escalation_targets_must_agree(self) -> None:
        errors = self.mutated(
            lambda d: d["loops"]["checkpoint_loop"].__setitem__("escalation_target", "REJECTED")
        )
        self.assertTrue(any("escalation_on_miss" in e for e in errors), errors)

    def test_the_escalation_target_must_be_a_real_state(self) -> None:
        errors = self.mutated(
            lambda d: d["long_task"].__setitem__("escalation_on_miss", "PANIC")
        )
        self.assertTrue(any("must be a declared state" in e for e in errors), errors)

    def test_the_miss_ceiling_must_match_the_loop_bound(self) -> None:
        errors = self.mutated(lambda d: d["long_task"].__setitem__("max_missed_checkpoints", 9))
        self.assertTrue(any("max_missed_checkpoints" in e for e in errors), errors)


class SupervisionCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store_path = Path(self.tmp.name) / "store"
        self.run_cli("--now", "0", "law", "create", "--title", "Long Build", "--metric", "ships")
        self.run_cli(
            "--now", "0", "case", "start", "--law", "LAW-001",
            "--name", "Six week build", "--request", "build it",
        )

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--store", str(self.store_path), *argv])
        return code, out.getvalue(), err.getvalue()

    def checkpoint(self, at: float, **fields) -> tuple[int, str, str]:
        summary = dict(SUMMARY, **fields)
        return self.run_cli(
            "--now", str(at), "case", "checkpoint", "--case", "CASE-001",
            "--completed", summary["completed"], "--blocked", summary["blocked"],
            "--next-step", summary["next_step"], "--eta", summary["eta"],
        )

    def test_starting_a_case_starts_the_clock(self) -> None:
        case = Store(self.store_path).load_case("CASE-001")
        self.assertEqual(case.last_checkpoint_at, 0)

    def test_reporting_on_time_exits_zero(self) -> None:
        code, out, _ = self.run_cli("--now", str(INTERVAL), "case", "supervise", "--case", "CASE-001")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("HEALTHY", out)

    def test_a_late_case_exits_blocked(self) -> None:
        code, out, _ = self.run_cli(
            "--now", str(DEADLINE + 1), "case", "supervise", "--case", "CASE-001"
        )
        self.assertEqual(code, EXIT_BLOCKED)
        self.assertIn("OVERDUE", out)

    def test_an_incomplete_report_is_refused(self) -> None:
        code, _, err = self.checkpoint(100, blocked="")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("incomplete progress summary", err)

    def test_a_checkpoint_is_stored_as_executive_evidence(self) -> None:
        code, _, _ = self.checkpoint(100)
        self.assertEqual(code, EXIT_OK)
        case = Store(self.store_path).load_case("CASE-001")
        self.assertEqual(len(case.checkpoints), 1)
        self.assertIn("progress_summary", case.artifacts)

    def test_repeating_a_report_exits_escalated(self) -> None:
        self.checkpoint(100)
        code, out, _ = self.checkpoint(200)
        self.assertEqual(code, EXIT_ESCALATED)
        self.assertIn("STAGNATED", out)

    def test_escalating_hands_the_case_to_its_own_guards(self) -> None:
        over = DEADLINE + INTERVAL * LONG_TASK["max_missed_checkpoints"]
        code, out, _ = self.run_cli(
            "--now", str(over), "case", "supervise", "--case", "CASE-001", "--escalate"
        )
        self.assertEqual(code, EXIT_ESCALATED)
        self.assertIn("executive authority", out)

        case = Store(self.store_path).load_case("CASE-001")
        self.assertEqual(case.facts["open_ambiguity_items"], 1)
        self.assertEqual(case.state, "NEW")  # supervision does not move the case

    def test_review_without_escalate_records_nothing(self) -> None:
        over = DEADLINE + INTERVAL * LONG_TASK["max_missed_checkpoints"]
        self.run_cli("--now", str(over), "case", "supervise", "--case", "CASE-001")
        case = Store(self.store_path).load_case("CASE-001")
        self.assertNotIn("open_ambiguity_items", case.facts)


if __name__ == "__main__":
    unittest.main()
