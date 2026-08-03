"""Offline tests for role agency: models producing a case's facts and artifacts."""

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
from runtime.agency import AgencyError, RoleAgency  # noqa: E402
from runtime.case import Case  # noqa: E402
from runtime.executor import CaseRunner, RunStatus  # noqa: E402
from runtime.roles import IsolationError  # noqa: E402
from runtime.session import GovernanceSession  # noqa: E402
from validate_governance import validate_config  # noqa: E402

CONFIG = json.loads((REPO_ROOT / "config" / "governance.json").read_text(encoding="utf-8"))


def scripted_session(scripts: dict[str, list[str]]) -> GovernanceSession:
    """A session whose roles replay canned replies instead of calling models."""
    session = GovernanceSession(copy.deepcopy(CONFIG))
    for role_name, replies in scripts.items():
        adapter = ScriptedAdapter(name=f"scripted_{role_name}", replies=replies)
        session.adapters[role_name] = adapter
        session.roles[role_name].adapter = adapter
    return session


def reply(facts: dict | None = None, artifacts: dict | None = None) -> str:
    return json.dumps({"facts": facts or {}, "artifacts": artifacts or {}})


HARNESS = {name: f"{name}-v1" for name in CONFIG["harness"]["required_artifacts"]}


class WriteAuthorityTest(unittest.TestCase):
    def role(self, name: str, replies: list[str]):
        return scripted_session({name: replies}).role(name)

    def test_a_role_may_write_its_own_keys(self) -> None:
        role = self.role("legislative", [])
        case = Case("CASE-001")
        written = role.apply_writes(case, {"facts": {"law": "LAW-001"}, "artifacts": {}})
        self.assertEqual(written, ["law"])
        self.assertEqual(case.facts["law"], "LAW-001")

    def test_writing_another_roles_key_is_refused(self) -> None:
        role = self.role("executive", [])
        with self.assertRaises(IsolationError) as caught:
            role.apply_writes(Case("CASE-001"), {"facts": {"red_line_violated": True}})
        self.assertIn("red_line_violated", str(caught.exception))
        self.assertIn("outside its authority", str(caught.exception))

    def test_the_executive_cannot_clear_its_own_verdict(self) -> None:
        """The role being judged must not be able to write the judgment."""
        role = self.role("executive", [])
        with self.assertRaises(IsolationError):
            role.apply_writes(Case("CASE-001"), {"facts": {"unresolved_law_items": 0}})

    def test_overreach_is_refused_wholesale_not_trimmed(self) -> None:
        role = self.role("legislative", [])
        case = Case("CASE-001")
        with self.assertRaises(IsolationError):
            role.apply_writes(
                case, {"facts": {"law": "LAW-001", "red_line_violated": False}}
            )
        self.assertNotIn("law", case.facts)

    def test_system_prompt_tells_the_model_its_write_scope(self) -> None:
        prompt = self.role("judiciary", []).system_prompt()
        self.assertIn("unresolved_law_items", prompt)
        self.assertIn("JSON", prompt)


class MaterialsTest(unittest.TestCase):
    def test_a_role_only_ever_sees_what_it_may_read(self) -> None:
        session = scripted_session({"judiciary": [reply()]})
        agency = RoleAgency(session)
        case = Case("CASE-001", facts={"user_request": "secret intake"}, artifacts=dict(HARNESS))
        case.state = "JUDICIARY"
        agency.act(case)

        _, prompt = session.adapters["judiciary"].asked[0]
        # `user_request` is not in the judiciary's may_read list.
        self.assertNotIn("secret intake", prompt)
        self.assertIn("harness_artifacts", prompt)

    def test_harness_and_case_artifacts_are_presented_separately(self) -> None:
        session = scripted_session({"judiciary": [reply()]})
        agency = RoleAgency(session)
        case = Case("CASE-001", artifacts={**HARNESS, "rework_diff_note": "note"})
        case.state = "JUDICIARY"
        materials = agency.materials(case)
        self.assertEqual(set(materials["harness_artifacts"]), set(HARNESS))
        self.assertEqual(set(materials["case_artifacts"]), {"rework_diff_note"})


class MalformedReplyTest(unittest.TestCase):
    def act_with(self, text: str) -> None:
        # Queued twice: the repair pass gets its round trip and still fails, so
        # these tests cover the outcome after repair rather than instead of it.
        session = scripted_session({"legislative": [text, text]})
        case = Case("CASE-001", facts={"user_request": "build it"})
        case.state = "LEGISLATIVE"
        RoleAgency(session).act(case)

    def test_non_json_is_surfaced_not_swallowed(self) -> None:
        with self.assertRaises(AgencyError):
            self.act_with("Sure! Here is the law you asked for.")

    def test_json_that_is_not_an_object_is_refused(self) -> None:
        with self.assertRaises(AgencyError):
            self.act_with('["law"]')

    def test_no_role_acts_in_a_terminal_state(self) -> None:
        session = scripted_session({"judiciary": []})
        case = Case("CASE-001")
        case.state = "PASSED"
        self.assertIsNone(RoleAgency(session).act(case))


class ModelDrivenRunTest(unittest.TestCase):
    def test_roles_drive_a_case_all_the_way_to_passed(self) -> None:
        session = scripted_session(
            {
                "legislative": [
                    reply(
                        facts={"law": "LAW-001"},
                        artifacts={"acceptance_criteria": "AC-1"},
                    )
                ],
                "executive": [
                    reply(
                        facts={"open_ambiguity_items": 0},
                        artifacts=dict(HARNESS),
                    )
                ],
                "judiciary": [
                    reply(
                        facts={
                            "unresolved_law_items": 0,
                            "defective_law_items": 0,
                            "red_line_violated": False,
                        }
                    )
                ],
            }
        )
        doc = copy.deepcopy(CONFIG)
        runner = CaseRunner(doc, agency=RoleAgency(session, doc))
        case = Case("CASE-001", facts={"user_request": "build it"}, artifacts={"user_request": "req"})

        result = runner.run(case)
        self.assertEqual(result.status, RunStatus.TERMINAL)
        self.assertEqual(case.state, "PASSED")
        self.assertEqual(case.facts["law"], "LAW-001")
        self.assertIn("evidence_bundle", case.artifacts)

    def test_a_judiciary_verdict_of_unproven_sends_the_case_back(self) -> None:
        session = scripted_session(
            {
                "legislative": [reply(facts={"law": "L"}, artifacts={"acceptance_criteria": "AC"})],
                "executive": [reply(facts={"open_ambiguity_items": 0}, artifacts=dict(HARNESS))],
                "judiciary": [
                    reply(
                        facts={
                            "unresolved_law_items": 2,
                            "defective_law_items": 0,
                            "red_line_violated": False,
                        },
                        artifacts={"amendment_reason": "-"},
                    )
                ],
            }
        )
        doc = copy.deepcopy(CONFIG)
        runner = CaseRunner(doc, agency=RoleAgency(session, doc))
        case = Case("CASE-001", facts={"user_request": "x"}, artifacts={"user_request": "req"})

        for _ in range(6):
            result = runner.step(case)
            if case.state == "REWORK" or result.status is not RunStatus.MOVED:
                break
        self.assertEqual(case.state, "REWORK")
        self.assertEqual(case.facts["unresolved_law_items"], 2)

    def test_the_executor_still_runs_with_no_agency_at_all(self) -> None:
        runner = CaseRunner(copy.deepcopy(CONFIG))
        self.assertIsNone(runner.agency)


class ConfigContractTest(unittest.TestCase):
    def mutated(self, mutate) -> list[str]:
        doc = copy.deepcopy(CONFIG)
        mutate(doc)
        return validate_config(doc)

    def test_shared_write_authority_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["role_isolation"]["executive"]["may_write"].append("red_line_violated")
        )
        self.assertTrue(any("already owned by" in e for e in errors), errors)

    def test_every_state_declares_who_acts_in_it(self) -> None:
        errors = self.mutated(lambda d: d["state_roles"].pop("JUDICIARY"))
        self.assertTrue(any("state_roles missing states" in e for e in errors), errors)

    def test_a_terminal_state_may_not_have_an_acting_role(self) -> None:
        errors = self.mutated(lambda d: d["state_roles"].__setitem__("PASSED", "judiciary"))
        self.assertTrue(any("must have no acting role" in e for e in errors), errors)

    def test_an_unknown_role_is_rejected(self) -> None:
        errors = self.mutated(lambda d: d["state_roles"].__setitem__("REWORK", "auditor"))
        self.assertTrue(any("not a declared role" in e for e in errors), errors)

    def test_empty_write_authority_is_rejected(self) -> None:
        errors = self.mutated(lambda d: d["role_isolation"]["judiciary"].__setitem__("may_write", []))
        self.assertTrue(any("may_write" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
