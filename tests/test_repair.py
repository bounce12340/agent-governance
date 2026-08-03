"""Offline tests for salvaging and repairing model replies."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from runtime.adapters import ScriptedAdapter  # noqa: E402
from runtime.agency import AgencyError, RoleAgency, extract_object  # noqa: E402
from runtime.case import Case  # noqa: E402
from runtime.session import GovernanceSession  # noqa: E402
from validate_governance import MAX_REPAIR_CEILING, validate_config  # noqa: E402

CONFIG = json.loads((REPO_ROOT / "config" / "governance.json").read_text(encoding="utf-8"))
PAYLOAD = {"facts": {"law": "LAW-001"}, "artifacts": {"acceptance_criteria": "AC"}}
GOOD_REPLY = json.dumps(PAYLOAD)


def session_with(replies: list[str], attempts: int | None = None):
    doc = copy.deepcopy(CONFIG)
    if attempts is not None:
        doc["model_replies"]["max_repair_attempts"] = attempts
    session = GovernanceSession(doc)
    adapter = ScriptedAdapter(name="scripted_legislative", replies=replies)
    session.adapters["legislative"] = adapter
    session.roles["legislative"].adapter = adapter
    return session, doc, adapter


def legislative_case() -> Case:
    case = Case("CASE-001", facts={"user_request": "build it"})
    case.state = "LEGISLATIVE"
    return case


class ExtractionTest(unittest.TestCase):
    """Salvaging costs no model call, so it happens before any repair."""

    def test_plain_json_is_read_directly(self) -> None:
        self.assertEqual(extract_object(GOOD_REPLY), PAYLOAD)

    def test_a_fenced_block_is_unwrapped(self) -> None:
        self.assertEqual(extract_object(f"```json\n{GOOD_REPLY}\n```"), PAYLOAD)

    def test_a_bare_fence_is_unwrapped(self) -> None:
        self.assertEqual(extract_object(f"```\n{GOOD_REPLY}\n```"), PAYLOAD)

    def test_json_buried_in_prose_is_recovered(self) -> None:
        wrapped = f"Certainly! Here is the law:\n\n{GOOD_REPLY}\n\nLet me know if you need more."
        self.assertEqual(extract_object(wrapped), PAYLOAD)

    def test_prose_alone_yields_nothing(self) -> None:
        self.assertIsNone(extract_object("I have written the law as requested."))

    def test_a_json_array_is_not_an_object(self) -> None:
        self.assertIsNone(extract_object('["law"]'))

    def test_empty_and_non_string_replies_are_handled(self) -> None:
        for value in ("", "   ", None, 42):
            with self.subTest(value=value):
                self.assertIsNone(extract_object(value))


class RepairTest(unittest.TestCase):
    def act(self, replies: list[str], attempts: int | None = None):
        session, doc, adapter = session_with(replies, attempts)
        case = legislative_case()
        written = RoleAgency(session, doc).act(case)
        return case, written, adapter

    def test_a_salvageable_reply_costs_no_repair_call(self) -> None:
        case, written, adapter = self.act([f"```json\n{GOOD_REPLY}\n```"])
        self.assertEqual(written, ["acceptance_criteria", "law"])
        self.assertEqual(len(adapter.asked), 1)
        self.assertEqual(case.reply_repairs, {})

    def test_prose_is_repaired_once_and_then_succeeds(self) -> None:
        case, written, adapter = self.act(["Sure, I wrote the law!", GOOD_REPLY])
        self.assertEqual(written, ["acceptance_criteria", "law"])
        self.assertEqual(len(adapter.asked), 2)
        self.assertEqual(case.reply_repairs, {"legislative": 1})

    def test_the_repair_prompt_quotes_the_bad_reply_and_demands_json(self) -> None:
        _, _, adapter = self.act(["Sure, I wrote the law!", GOOD_REPLY])
        _, repair_prompt = adapter.asked[1]
        self.assertIn("Sure, I wrote the law!", repair_prompt)
        self.assertIn("JSON object only", repair_prompt)

    def test_a_role_that_never_returns_json_still_fails(self) -> None:
        with self.assertRaises(AgencyError) as caught:
            self.act(["nope", "still nope"])
        self.assertIn("1 repair attempt", str(caught.exception))

    def test_the_repair_budget_is_the_ceiling_not_a_suggestion(self) -> None:
        session, doc, adapter = session_with(["a", "b", "c", "d", GOOD_REPLY], attempts=2)
        with self.assertRaises(AgencyError):
            RoleAgency(session, doc).act(legislative_case())
        # One original call plus exactly two repairs, then it gives up.
        self.assertEqual(len(adapter.asked), 3)

    def test_zero_attempts_disables_repair_entirely(self) -> None:
        session, doc, adapter = session_with(["prose", GOOD_REPLY], attempts=0)
        with self.assertRaises(AgencyError):
            RoleAgency(session, doc).act(legislative_case())
        self.assertEqual(len(adapter.asked), 1)

    def test_repairs_survive_serialisation(self) -> None:
        case, _, _ = self.act(["prose first", GOOD_REPLY])
        restored = Case.from_dict(json.loads(json.dumps(case.to_dict())))
        self.assertEqual(restored.reply_repairs, {"legislative": 1})

    def test_a_repaired_reply_is_still_bound_by_write_authority(self) -> None:
        """Repair recovers the format; it does not widen what a role may write."""
        from runtime.roles import IsolationError

        overreach = json.dumps({"facts": {"red_line_violated": True}})
        with self.assertRaises(IsolationError):
            self.act(["prose", overreach])


class ConfigContractTest(unittest.TestCase):
    def mutated(self, mutate) -> list[str]:
        doc = copy.deepcopy(CONFIG)
        mutate(doc)
        return validate_config(doc)

    def test_shipped_config_passes(self) -> None:
        self.assertEqual(validate_config(copy.deepcopy(CONFIG)), [])

    def test_a_negative_budget_is_rejected(self) -> None:
        errors = self.mutated(lambda d: d["model_replies"].__setitem__("max_repair_attempts", -1))
        self.assertTrue(any("non-negative integer" in e for e in errors), errors)

    def test_an_unbounded_budget_is_rejected(self) -> None:
        """No unbounded retries, one level down from the loop layer."""
        errors = self.mutated(lambda d: d["model_replies"].__setitem__("max_repair_attempts", 99))
        self.assertTrue(any(str(MAX_REPAIR_CEILING) in e for e in errors), errors)

    def test_a_boolean_is_not_a_budget(self) -> None:
        errors = self.mutated(lambda d: d["model_replies"].__setitem__("max_repair_attempts", True))
        self.assertTrue(any("non-negative integer" in e for e in errors), errors)

    def test_missing_keys_are_reported(self) -> None:
        errors = self.mutated(lambda d: d["model_replies"].pop("repair_instruction"))
        self.assertTrue(any("model_replies missing keys" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
