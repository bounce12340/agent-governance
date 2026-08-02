"""Flat-file store for laws and cases.

JSON files on disk, standard library only. A governance record that needs a
database to be read back is a governance record nobody will audit.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from runtime.case import Case

DEFAULT_STORE = ".ai-gov"
ID_PATTERN = re.compile(r"^[A-Z]+-(\d+)$")


class StoreError(RuntimeError):
    pass


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
        (self.laws / f"{law_id}.json").write_text(
            json.dumps(law, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
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

    def save_case(self, case: Case) -> None:
        self.prepare()
        (self.cases / f"{case.case_id}.json").write_text(
            json.dumps(case.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

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
