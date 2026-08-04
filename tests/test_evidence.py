"""Offline tests: every artifact the graph asks for has an author.

The graph checks prove a state is reachable. They say nothing about whether a
case can actually get there — an edge requiring evidence no role may write is
an edge that is reachable on paper and impassable in practice.
"""

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
from runtime.executor import CaseRunner, RunStatus  # noqa: E402
from validate_governance import validate_config  # noqa: E402

CONFIG = json.loads((REPO_ROOT / "config" / "governance.json").read_text(encoding="utf-8"))


def writable_keys(doc: dict) -> set[str]:
    keys: set[str] = set()
    for role_cfg in doc["role_isolation"].values():
        keys |= set(role_cfg["may_write"])
    return keys


class ProducibilityTest(unittest.TestCase):
    def mutated(self, mutate) -> list[str]:
        doc = copy.deepcopy(CONFIG)
        mutate(doc)
        return validate_config(doc)

    def test_shipped_config_passes(self) -> None:
        self.assertEqual(validate_config(copy.deepcopy(CONFIG)), [])

    def test_every_required_evidence_has_an_author(self) -> None:
        producible = writable_keys(CONFIG) | set(CONFIG["intake_artifacts"])
        for source, targets in CONFIG["graph"]["edges"].items():
            for target, edge in targets.items():
                with self.subTest(edge=f"{source}->{target}"):
                    self.assertIn(edge["required_evidence"], producible)

    def test_every_per_iteration_artifact_has_an_author(self) -> None:
        producible = writable_keys(CONFIG) | set(CONFIG["intake_artifacts"])
        for name, loop in CONFIG["loops"].items():
            with self.subTest(loop=name):
                self.assertIn(loop["per_iteration_artifact"], producible)

    def test_unwritable_edge_evidence_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["graph"]["edges"]["JUDICIARY"]["PASSED"].__setitem__(
                "required_evidence", "notarised_affidavit"
            )
        )
        self.assertTrue(any("cannot be produced" in e for e in errors), errors)
        self.assertTrue(any("notarised_affidavit" in e for e in errors), errors)

    def test_unwritable_loop_artifact_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["loops"]["rework_loop"].__setitem__(
                "per_iteration_artifact", "a_note_nobody_writes"
            )
        )
        self.assertTrue(any("cannot be produced" in e for e in errors), errors)

    def test_removing_the_writer_breaks_the_edge_that_needed_it(self) -> None:
        """The evidence is unchanged; the author is gone. Still unproducible."""

        def drop_writer(doc: dict) -> None:
            doc["role_isolation"]["executive"]["may_write"].remove("output_snapshot")

        errors = self.mutated(drop_writer)
        self.assertTrue(any("output_snapshot" in e for e in errors), errors)

    def test_intake_artifacts_count_as_producible(self) -> None:
        """`user_request` is in no role's may_write and must still be allowed.

        `NEW -> LEGISLATIVE` requires it. If intake did not count, the very
        first edge of the graph would be judged impassable.
        """
        self.assertNotIn("user_request", writable_keys(CONFIG))
        self.assertIn("user_request", CONFIG["intake_artifacts"])
        self.assertEqual(validate_config(copy.deepcopy(CONFIG)), [])

    def test_empty_intake_is_rejected(self) -> None:
        errors = self.mutated(lambda d: d.__setitem__("intake_artifacts", []))
        self.assertTrue(any("intake_artifacts" in e for e in errors), errors)

    def test_an_intake_artifact_a_role_can_also_write_is_rejected(self) -> None:
        """Two authors for one artifact is the ambiguity may_write disjointness exists to stop."""
        errors = self.mutated(
            lambda d: d["role_isolation"]["executive"]["may_write"].append("user_request")
        )
        self.assertTrue(any("intake_artifacts also claimed" in e for e in errors), errors)


class ImpassableEdgeTest(unittest.TestCase):
    """What the validator is actually preventing, demonstrated at run time."""

    def test_a_case_stops_dead_at_evidence_nobody_can_write(self) -> None:
        doc = copy.deepcopy(CONFIG)
        doc["graph"]["edges"]["NEW"]["LEGISLATIVE"]["required_evidence"] = "notarised_affidavit"
        runner = CaseRunner(doc)
        case = Case("CASE-001", facts={"user_request": "build it"}, artifacts={"user_request": "req"})

        result = runner.run(case, max_steps=10)
        self.assertEqual(result.status, RunStatus.BLOCKED)
        self.assertIn("notarised_affidavit", result.note)
        self.assertEqual(case.state, "NEW")


if __name__ == "__main__":
    unittest.main()
