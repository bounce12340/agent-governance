"""Long-task supervision: enforce the checkpoints the config already declares.

`long_task` has specified an interval, a grace period, a miss ceiling and an
escalation target since the framework's first release, and `checkpoint_loop`
has declared bounds for it, but nothing ever counted a missed check-in. This
module is what makes those numbers bite.

The clock is an argument, never a hidden call. A supervisor that reads the wall
clock internally cannot be tested, and a supervision rule nobody tests is the
same kind of claim this layer exists to retire.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .case import Case


class SupervisionError(RuntimeError):
    pass


class CheckpointStatus(str, Enum):
    DISABLED = "DISABLED"
    HEALTHY = "HEALTHY"
    OVERDUE = "OVERDUE"
    STAGNATED = "STAGNATED"
    ESCALATED = "ESCALATED"


@dataclass
class SupervisionResult:
    status: CheckpointStatus
    note: str
    missed: int = 0

    @property
    def healthy(self) -> bool:
        return self.status in {CheckpointStatus.HEALTHY, CheckpointStatus.DISABLED}


class CheckpointSupervisor:
    """Tracks whether a long-running case is still reporting."""

    def __init__(self, doc: dict[str, Any]) -> None:
        long_task = doc.get("long_task") or {}
        self.enabled = long_task.get("enabled") is True
        self.required_periodic = long_task.get("require_periodic_checkpoints") is True
        self.required_fields: list[str] = list(long_task.get("require_progress_summary") or [])
        self.interval = int(long_task.get("checkpoint_interval_minutes") or 0) * 60
        self.grace = int(long_task.get("checkpoint_grace_minutes") or 0) * 60
        self.max_missed = int(long_task.get("max_missed_checkpoints") or 0)
        self.escalation_target = long_task.get("escalation_on_miss")

        loop = (doc.get("loops") or {}).get("checkpoint_loop") or {}
        self.artifact = loop.get("per_iteration_artifact") or "progress_summary"
        self.stagnation_rule = loop.get("stagnation_rule") or "identical_progress_summary_twice"

    # --- clock -------------------------------------------------------------

    @staticmethod
    def _now(now: float | None) -> float:
        return time.time() if now is None else float(now)

    def start(self, case: Case, now: float | None = None) -> None:
        """Start the checkpoint clock. Nothing can be late before this."""
        case.last_checkpoint_at = self._now(now)

    def deadline(self, case: Case) -> float | None:
        if case.last_checkpoint_at is None:
            return None
        return case.last_checkpoint_at + self.interval + self.grace

    # --- reporting ---------------------------------------------------------

    def record(self, case: Case, summary: dict[str, Any], now: float | None = None) -> SupervisionResult:
        """Record a progress checkpoint.

        An incomplete report is not a report. The same reasoning the harness
        gate applies to evidence applies here: a check-in missing `blocked` or
        `eta` looks like progress while withholding the part that would show
        there is none.
        """
        if not isinstance(summary, dict):
            raise SupervisionError("a progress summary must be a mapping")
        missing = [field for field in self.required_fields if not str(summary.get(field, "")).strip()]
        if missing:
            raise SupervisionError(
                f"incomplete progress summary, missing: {', '.join(missing)}"
            )

        stamp = self._now(now)
        entry = {field: summary[field] for field in self.required_fields}
        previous = case.checkpoints[-1] if case.checkpoints else None

        case.checkpoints.append({**entry, "at": stamp})
        case.last_checkpoint_at = stamp
        case.missed_checkpoints = 0

        if previous is not None and {
            field: previous.get(field) for field in self.required_fields
        } == entry:
            return SupervisionResult(
                CheckpointStatus.STAGNATED,
                f"{self.stagnation_rule}: this checkpoint repeats the previous one",
            )
        return SupervisionResult(CheckpointStatus.HEALTHY, "checkpoint recorded")

    # --- review ------------------------------------------------------------

    def review(self, case: Case, now: float | None = None) -> SupervisionResult:
        """How many checkpoints has this case missed, and does that escalate?

        The count is derived from elapsed time rather than incremented on each
        call, so reviewing twice cannot inflate it.
        """
        if not self.enabled or not self.required_periodic:
            return SupervisionResult(CheckpointStatus.DISABLED, "long-task supervision is off")
        if case.last_checkpoint_at is None:
            return SupervisionResult(CheckpointStatus.HEALTHY, "no checkpoint clock started")
        if self.interval < 1:
            return SupervisionResult(CheckpointStatus.DISABLED, "no checkpoint interval declared")

        # "Due by X" means X is still on time; only past it does a checkpoint
        # count as missed, and each further interval adds one more.
        deadline = self.deadline(case)
        stamp = self._now(now)
        missed = 0 if stamp <= deadline else 1 + int((stamp - deadline) // self.interval)
        case.missed_checkpoints = missed

        if missed == 0:
            return SupervisionResult(CheckpointStatus.HEALTHY, "reporting on time")
        if missed <= self.max_missed:
            return SupervisionResult(
                CheckpointStatus.OVERDUE,
                f"missed {missed} of {self.max_missed} allowed checkpoints",
                missed,
            )
        return SupervisionResult(
            CheckpointStatus.ESCALATED,
            f"missed {missed} checkpoints, over the limit of {self.max_missed}; "
            f"escalating to {self.escalation_target}",
            missed,
        )

    # --- escalation --------------------------------------------------------

    def escalate(self, case: Case, session: Any, reason: str) -> list[str]:
        """Escalate through the executive's own authority.

        Supervision does not move the case itself. It records what the
        executive would report — an open ambiguity it cannot resolve — and lets
        the case's own guards route it. Writing the transition directly would
        bypass the graph, and the escalation target is reachable from
        EXECUTIVE precisely because this is the executive raising its hand.
        """
        role = session.role("executive")
        return role.apply_writes(
            case,
            {
                "facts": {"open_ambiguity_items": case.fact("open_ambiguity_items") + 1},
                "artifacts": {"ambiguity_notes": reason},
            },
        )
