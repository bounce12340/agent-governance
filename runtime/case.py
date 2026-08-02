"""The unit of work the state machine moves.

A case carries three separable things: `facts`, which guards read to decide
routing; `artifacts`, which are the harness evidence; and `history`, which is
the audit trail. Keeping facts out of artifacts matters — evidence is what the
judiciary reviews, not what the router branches on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ENTRY_STATE = "NEW"


@dataclass
class Case:
    case_id: str
    state: str = ENTRY_STATE
    facts: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    invalid_artifacts: set[str] = field(default_factory=set)
    history: list[dict[str, Any]] = field(default_factory=list)
    loop_iterations: dict[str, int] = field(default_factory=dict)
    loop_evidence: dict[str, list[Any]] = field(default_factory=dict)

    def fact(self, name: str, default: Any = 0) -> Any:
        return self.facts.get(name, default)

    def iterations(self, loop_name: str) -> int:
        return self.loop_iterations.get(loop_name, 0)

    def record(self, source: str, target: str, guard: str, evidence: str, loop: str | None) -> None:
        self.history.append(
            {
                "from": source,
                "to": target,
                "guard": guard,
                "evidence": evidence,
                "loop": loop,
            }
        )
        self.state = target

    def trail(self) -> str:
        """The route taken, for a verdict or a post-mortem."""
        if not self.history:
            return self.state
        steps = [self.history[0]["from"]] + [entry["to"] for entry in self.history]
        return " -> ".join(steps)
