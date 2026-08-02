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
    artifact_failures: dict[str, list[str]] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    loop_iterations: dict[str, int] = field(default_factory=dict)
    loop_evidence: dict[str, list[Any]] = field(default_factory=dict)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    last_checkpoint_at: float | None = None
    missed_checkpoints: int = 0

    def fact(self, name: str, default: Any = 0) -> Any:
        return self.facts.get(name, default)

    def iterations(self, loop_name: str) -> int:
        return self.loop_iterations.get(loop_name, 0)

    def record(
        self,
        source: str,
        target: str,
        guard: str,
        evidence: str,
        loop: str | None,
        note: str | None = None,
    ) -> None:
        entry = {
            "from": source,
            "to": target,
            "guard": guard,
            "evidence": evidence,
            "loop": loop,
        }
        if note:
            # An escalation hop is taken because a loop gave out, not because
            # the edge's guard was satisfied. Recording only the guard would
            # put a false reason in the audit trail.
            entry["escalation"] = note
        self.history.append(entry)
        self.state = target

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "state": self.state,
            "facts": self.facts,
            "artifacts": self.artifacts,
            "invalid_artifacts": sorted(self.invalid_artifacts),
            "artifact_failures": self.artifact_failures,
            "history": self.history,
            "loop_iterations": self.loop_iterations,
            "loop_evidence": self.loop_evidence,
            "checkpoints": self.checkpoints,
            "last_checkpoint_at": self.last_checkpoint_at,
            "missed_checkpoints": self.missed_checkpoints,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Case":
        return cls(
            case_id=data["case_id"],
            state=data.get("state", ENTRY_STATE),
            facts=data.get("facts") or {},
            artifacts=data.get("artifacts") or {},
            invalid_artifacts=set(data.get("invalid_artifacts") or []),
            artifact_failures=data.get("artifact_failures") or {},
            history=data.get("history") or [],
            loop_iterations=data.get("loop_iterations") or {},
            loop_evidence=data.get("loop_evidence") or {},
            checkpoints=data.get("checkpoints") or [],
            last_checkpoint_at=data.get("last_checkpoint_at"),
            missed_checkpoints=data.get("missed_checkpoints") or 0,
        )

    def trail(self) -> str:
        """The route taken, for a verdict or a post-mortem."""
        if not self.history:
            return self.state
        steps = [self.history[0]["from"]] + [entry["to"] for entry in self.history]
        return " -> ".join(steps)
