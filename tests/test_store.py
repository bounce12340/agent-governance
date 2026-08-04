"""Offline tests for the record store: atomic writes and lost-update refusal.

Two operators changing one case at once is a governance event. Keeping the last
write silently would erase whichever decision lost the race, and the audit trail
would not show that it happened.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ai_gov.store import ConflictError, Store, StoreError, write_atomically  # noqa: E402
from runtime.case import Case  # noqa: E402


class StoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.store = Store(self.root)
        self.store.prepare()

    def seed(self) -> Case:
        case = Case(case_id=self.store.new_case_id(), facts={"user_request": "build it"})
        self.store.save_case(case)
        return case


class VersionTest(StoreTestCase):
    def test_a_new_case_starts_at_version_zero_and_lands_at_one(self) -> None:
        case = Case(case_id="CASE-001")
        self.assertEqual(case.version, 0)
        self.store.save_case(case)
        self.assertEqual(case.version, 1)
        self.assertEqual(self.store.stored_version("CASE-001"), 1)

    def test_each_save_advances_the_version(self) -> None:
        case = self.seed()
        for expected in (2, 3, 4):
            self.store.save_case(case)
            self.assertEqual(case.version, expected)
            self.assertEqual(self.store.stored_version(case.case_id), expected)

    def test_the_version_survives_a_round_trip(self) -> None:
        case = self.seed()
        self.store.save_case(case)
        self.assertEqual(self.store.load_case(case.case_id).version, case.version)

    def test_an_unwritten_case_has_no_stored_version(self) -> None:
        self.assertIsNone(self.store.stored_version("CASE-404"))

    def test_loading_a_missing_case_is_an_error_not_an_empty_case(self) -> None:
        with self.assertRaises(StoreError):
            self.store.load_case("CASE-404")


class ConflictTest(StoreTestCase):
    def test_a_stale_writer_is_refused(self) -> None:
        original = self.seed()
        first = self.store.load_case(original.case_id)
        second = self.store.load_case(original.case_id)

        first.facts["unresolved_law_items"] = 0
        self.store.save_case(first)

        second.facts["unresolved_law_items"] = 7
        with self.assertRaises(ConflictError) as caught:
            self.store.save_case(second)
        self.assertIn(original.case_id, str(caught.exception))

    def test_the_winning_write_is_the_one_on_disk(self) -> None:
        original = self.seed()
        first = self.store.load_case(original.case_id)
        second = self.store.load_case(original.case_id)

        first.facts["red_line_violated"] = False
        self.store.save_case(first)
        second.facts["red_line_violated"] = True
        with self.assertRaises(ConflictError):
            self.store.save_case(second)

        self.assertIs(self.store.load_case(original.case_id).fact("red_line_violated"), False)

    def test_a_refused_write_leaves_the_version_untouched(self) -> None:
        """A caller that retries must not compare against a version never stored."""
        original = self.seed()
        stale = self.store.load_case(original.case_id)
        self.store.save_case(self.store.load_case(original.case_id))

        before = stale.version
        with self.assertRaises(ConflictError):
            self.store.save_case(stale)
        self.assertEqual(stale.version, before)

    def test_reloading_lets_the_loser_retry(self) -> None:
        original = self.seed()
        stale = self.store.load_case(original.case_id)
        self.store.save_case(self.store.load_case(original.case_id))
        with self.assertRaises(ConflictError):
            self.store.save_case(stale)

        fresh = self.store.load_case(original.case_id)
        fresh.facts["unresolved_law_items"] = 7
        self.store.save_case(fresh)
        self.assertEqual(self.store.load_case(original.case_id).fact("unresolved_law_items"), 7)

    def test_a_second_save_of_the_same_object_is_not_a_conflict(self) -> None:
        """One writer editing repeatedly is the normal case, not a race."""
        case = self.seed()
        case.facts["open_ambiguity_items"] = 1
        self.store.save_case(case)
        case.facts["open_ambiguity_items"] = 0
        self.store.save_case(case)
        self.assertEqual(self.store.load_case(case.case_id).fact("open_ambiguity_items"), 0)


class AtomicWriteTest(StoreTestCase):
    def test_a_reader_never_sees_half_a_record(self) -> None:
        path = self.root / "record.json"
        write_atomically(path, json.dumps({"a": 1}) + "\n")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 1})

    def test_a_failed_write_leaves_no_temporary_file(self) -> None:
        path = self.root / "record.json"
        with self.assertRaises(TypeError):
            write_atomically(path, object())  # type: ignore[arg-type]
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_a_failed_write_does_not_destroy_the_previous_record(self) -> None:
        path = self.root / "record.json"
        write_atomically(path, '{"kept": true}\n')
        with self.assertRaises(TypeError):
            write_atomically(path, object())  # type: ignore[arg-type]
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"kept": True})

    def test_the_temporary_file_shares_the_destination_directory(self) -> None:
        """os.replace is only atomic within one filesystem."""
        path = self.root / "record.json"
        write_atomically(path, "{}\n")
        self.assertEqual(os.stat(path).st_dev, os.stat(self.root).st_dev)


if __name__ == "__main__":
    unittest.main()
