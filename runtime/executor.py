"""Execute the state machine the config describes.

Nothing here hardcodes the flow. States, edges, guards, evidence requirements,
loop bounds and terminal states all come from `config/governance.yaml`, so
changing the governance model is a config change that the validator checks
before this ever runs.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from .case import Case
from .checks import failures as artifact_failures
from .guards import GUARDS


class ExecutionError(RuntimeError):
    pass


class NondeterministicRouting(ExecutionError):
    """More than one guard was true on the same fan-out.

    Guard mutual exclusion is what makes routing reviewable. Two open doors
    means the flow depends on dict ordering, so this is refused rather than
    resolved by picking one.
    """


class RunStatus(str, Enum):
    TERMINAL = "TERMINAL"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"
    STEP_LIMIT = "STEP_LIMIT"
    MOVED = "MOVED"


class StepResult:
    def __init__(self, status: RunStatus, note: str = "", target: str | None = None) -> None:
        self.status = status
        self.note = note
        self.target = target

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"<StepResult {self.status.value} {self.note}>"


class CaseRunner:
    """Moves a case through the declared graph, one guarded edge at a time."""

    def __init__(self, doc: dict[str, Any], agency: Any | None = None) -> None:
        self.doc = doc
        # Optional on purpose: with no agency the runner is a pure state
        # machine, which is what makes the routing testable without a model.
        self.agency = agency
        graph = doc.get("graph") or {}
        harness = doc.get("harness") or {}

        self.edges: dict[str, dict[str, dict[str, str]]] = graph.get("edges") or {}
        self.terminal_states = set(graph.get("terminal_states") or [])
        self.required_artifacts: list[str] = list(harness.get("required_artifacts") or [])
        self.gate_behavior: dict[str, str] = harness.get("gate_behavior") or {}
        self.artifact_checks: dict[str, list[str]] = harness.get("artifact_checks") or {}
        self.loops: dict[str, dict[str, Any]] = doc.get("loops") or {}

        # The first edge of a declared path is that loop's entry edge, so
        # taking it is what counts as one iteration.
        self.loop_entry_edges: dict[tuple[str, str], str] = {}
        for name, loop in self.loops.items():
            for path in loop.get("paths") or []:
                if isinstance(path, list) and len(path) >= 2:
                    self.loop_entry_edges[(path[0], path[1])] = name

    # --- context the guards read ------------------------------------------

    def loop_bound(self, loop_name: str) -> int:
        return int(self.loops[loop_name]["max_iterations"])

    # --- the harness gate --------------------------------------------------

    def gate_check(self, case: Case) -> str | None:
        """Return a gate verdict when the case may not leave HARNESS_SUBMITTED.

        Missing evidence stops the case here. Invalid evidence does not: the
        config says invalid artifacts mean `REWORK`, and the only lawful route
        to `REWORK` runs through the judiciary. So the gate marks what failed
        and lets the case go be judged — which is what turns
        `gate_behavior.invalid_artifacts` from a setting nothing could reach
        into a description of what actually happens.
        """
        missing = [name for name in self.required_artifacts if name not in case.artifacts]
        if missing:
            verdict = self.gate_behavior.get("missing_artifacts", "INCOMPLETE")
            return f"{verdict}: missing {', '.join(sorted(missing))}"

        # Recomputed every pass, so repairing an artifact clears its mark and
        # the rework loop can actually converge.
        case.artifact_failures = artifact_failures(case.artifacts, self.artifact_checks)
        case.invalid_artifacts = set(case.artifact_failures)
        return None

    # --- one step ----------------------------------------------------------

    def step(self, case: Case) -> StepResult:
        if case.state in self.terminal_states:
            return StepResult(RunStatus.TERMINAL, f"case ended at {case.state}")

        if self.agency is not None:
            self.agency.act(case)

        if case.state == "HARNESS_SUBMITTED":
            blocked = self.gate_check(case)
            if blocked:
                return StepResult(RunStatus.BLOCKED, blocked)

        targets = self.edges.get(case.state) or {}
        if not targets:
            return StepResult(RunStatus.BLOCKED, f"{case.state} has no outgoing edge")

        open_edges = []
        for target, edge in targets.items():
            guard_name = edge.get("guard", "")
            guard_fn = GUARDS.get(guard_name)
            if guard_fn is None:
                raise ExecutionError(f"no implementation for guard: {guard_name}")
            if guard_fn(case, self):
                open_edges.append((target, edge, guard_name))

        if not open_edges:
            return StepResult(
                RunStatus.BLOCKED, f"no guard is satisfied at {case.state}"
            )
        if len(open_edges) > 1:
            names = ", ".join(sorted(name for _, _, name in open_edges))
            raise NondeterministicRouting(
                f"{case.state} has more than one satisfied guard: {names}"
            )

        target, edge, guard_name = open_edges[0]
        evidence = edge.get("required_evidence", "")
        if evidence and evidence not in case.artifacts:
            return StepResult(
                RunStatus.BLOCKED,
                f"{case.state} -> {target} needs evidence: {evidence}",
            )

        loop_name = self.loop_entry_edges.get((case.state, target))
        if loop_name:
            stalled = self.account_for_loop(case, loop_name)
            if stalled:
                case.record(case.state, target, guard_name, evidence, loop_name)
                return self.escalate(case, loop_name, stalled)

        case.record(case.state, target, guard_name, evidence, loop_name)
        return StepResult(RunStatus.MOVED, f"{guard_name} -> {target}", target)

    # --- loop accounting ---------------------------------------------------

    def account_for_loop(self, case: Case, loop_name: str) -> str | None:
        """Count one iteration and report stagnation.

        Counting alone only limits how long a case spins; comparing the
        per-iteration artifact is what detects spinning in place.
        """
        loop = self.loops[loop_name]
        case.loop_iterations[loop_name] = case.iterations(loop_name) + 1

        artifact_name = loop.get("per_iteration_artifact", "")
        seen = case.loop_evidence.setdefault(loop_name, [])
        seen.append(case.artifacts.get(artifact_name))
        if len(seen) >= 2 and seen[-1] is not None and seen[-1] == seen[-2]:
            return loop.get("stagnation_rule", "stagnation")
        return None

    def escalate(self, case: Case, loop_name: str, reason: str) -> StepResult:
        """Send the case to the loop's escalation target if the graph allows it.

        Escalation cannot teleport. If the target is not reachable in one legal
        transition, the run halts and names it instead — jumping would violate
        the same graph invariants the validator enforces.
        """
        target = self.loops[loop_name].get("escalation_target", "")
        note = f"{loop_name} stagnated ({reason}), escalating to {target}"
        edge = (self.edges.get(case.state) or {}).get(target)
        if edge is None:
            return StepResult(RunStatus.ESCALATED, f"{note}; no legal edge from {case.state}")
        case.record(case.state, target, edge.get("guard", ""), edge.get("required_evidence", ""), loop_name)
        return StepResult(RunStatus.ESCALATED, note, target)

    # --- run to completion -------------------------------------------------

    def run(self, case: Case, max_steps: int = 100) -> StepResult:
        result = StepResult(RunStatus.BLOCKED, "no steps taken")
        for _ in range(max_steps):
            result = self.step(case)
            if result.status in {RunStatus.TERMINAL, RunStatus.BLOCKED, RunStatus.ESCALATED}:
                return result
        return StepResult(RunStatus.STEP_LIMIT, f"stopped after {max_steps} steps")
