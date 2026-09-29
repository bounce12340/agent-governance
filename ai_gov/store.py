"""Flat-file store for laws and cases.

JSON files on disk, standard library only. A governance record that needs a
database to be read back is a governance record nobody will audit.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from runtime.case import Case

DEFAULT_STORE = ".ai-gov"
ID_PATTERN = re.compile(r"^[A-Z]+-(\d+)$")


class StoreError(RuntimeError):
    pass


class ConflictError(StoreError):
    """Someone else wrote this case since it was read.

    Refused rather than overwritten. Two operators changing one case at once is
    a governance event — silently keeping the last write would erase whichever
    decision lost the race, and the audit trail would not show that it
    happened.
    """


def write_atomically(path: Path, text: str) -> None:
    """Write via a temp file and rename, so a reader never sees half a record."""
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class Store:
    def __init__(self, root: Path | str | None = None) -> None:
        if root is None:
            root = os.environ.get("AI_GOV_STORE", DEFAULT_STORE)
        self.root = Path(root)
        self.laws = self.root / "laws"
        self.cases = self.root / "cases"

    def prepare(self) -> None:
        self.laws.mkdir(parents=True, exist_ok=True)
        self.cases.mkdir(parents=True, exist_ok=True)

    # --- ids ---------------------------------------------------------------

    def next_id(self, prefix: str, folder: Path) -> str:
        """Allocate the next id. Sequential and gap-tolerant, never random."""
        highest = 0
        if folder.exists():
            for path in folder.glob(f"{prefix}-*.json"):
                match = ID_PATTERN.match(path.stem)
                if match:
                    highest = max(highest, int(match.group(1)))
        return f"{prefix}-{highest + 1:03d}"

    # --- laws --------------------------------------------------------------

    def create_law(self, title: str, metrics: list[str], red_lines: list[str]) -> dict[str, Any]:
        self.prepare()
        law_id = self.next_id("LAW", self.laws)
        law = {
            "law_id": law_id,
            "title": title,
            "acceptance_criteria": list(metrics),
            "red_lines": list(red_lines),
        }
        write_atomically(
            self.laws / f"{law_id}.json",
            json.dumps(law, indent=2, ensure_ascii=False) + "\n",
        )
        return law

    def load_law(self, law_id: str) -> dict[str, Any]:
        path = self.laws / f"{law_id}.json"
        if not path.exists():
            raise StoreError(f"no such law: {law_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    # --- cases -------------------------------------------------------------

    def new_case_id(self) -> str:
        self.prepare()
        return self.next_id("CASE", self.cases)

    def stored_version(self, case_id: str) -> int | None:
        path = self.cases / f"{case_id}.json"
        if not path.exists():
            return None
        return int(json.loads(path.read_text(encoding="utf-8")).get("version") or 0)

    def save_case(self, case: Case) -> None:
        """Compare-and-set on the case's version, then write atomically.

        The version the case was loaded with must still be the one on disk. If
        it is not, another writer got there first and this write is refused.
        """
        self.prepare()
        on_disk = self.stored_version(case.case_id)
        if on_disk is not None and on_disk != case.version:
            raise ConflictError(
                f"{case.case_id} changed underneath this write: "
                f"loaded version {case.version}, on disk {on_disk}"
            )
        case.version += 1
        try:
            write_atomically(
                self.cases / f"{case.case_id}.json",
                json.dumps(case.to_dict(), indent=2, ensure_ascii=False) + "\n",
            )
        except BaseException:
            # Leave the in-memory case matching what is actually stored, so a
            # caller that retries is not comparing against a version that never
            # reached disk.
            case.version -= 1
            raise

    def load_case(self, case_id: str) -> Case:
        path = self.cases / f"{case_id}.json"
        if not path.exists():
            raise StoreError(f"no such case: {case_id}")
        return Case.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_cases(self) -> list[Case]:
        if not self.cases.exists():
            return []
        return [
            Case.from_dict(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(self.cases.glob("CASE-*.json"))
        ]
