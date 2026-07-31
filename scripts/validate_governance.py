#!/usr/bin/env python3
"""Validate the governance config and core governance artifacts.

Supports both JSON and YAML config files.
YAML support is implemented locally so the script works without extra runtime
packages.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_STATES = {
    "NEW",
    "LEGISLATIVE",
    "EXECUTIVE",
    "HARNESS_SUBMITTED",
    "JUDICIARY",
    "PASSED",
    "REWORK",
    "REJECTED",
    "LAW_AMENDMENT_REQUEST",
    "LAW_CLARIFICATION_REQUEST",
}

REQUIRED_TRANSITIONS = {
    "NEW": {"LEGISLATIVE"},
    "LEGISLATIVE": {"EXECUTIVE"},
    "EXECUTIVE": {"HARNESS_SUBMITTED", "LAW_CLARIFICATION_REQUEST"},
    "HARNESS_SUBMITTED": {"JUDICIARY"},
    "JUDICIARY": {"PASSED", "REWORK", "REJECTED", "LAW_AMENDMENT_REQUEST"},
    "REWORK": {"EXECUTIVE", "REJECTED"},
    "LAW_AMENDMENT_REQUEST": {"LEGISLATIVE"},
    "LAW_CLARIFICATION_REQUEST": {"LEGISLATIVE", "EXECUTIVE"},
}

REQUIRED_ARTIFACTS = {
    "test_plan",
    "evidence_bundle",
    "output_snapshot",
    "failure_mode_notes",
}

REQUIRED_LONG_TASK_KEYS = {
    "enabled",
    "require_periodic_checkpoints",
    "checkpoint_interval_minutes",
    "checkpoint_grace_minutes",
    "max_missed_checkpoints",
    "escalation_on_miss",
    "require_progress_summary",
}

REQUIRED_PROGRESS_FIELDS = {"completed", "blocked", "next_step", "eta"}

ROLE_NAMES = {"legislative", "executive", "judiciary"}

REQUIRED_LOOP_NAMES = {
    "rework_loop",
    "clarification_loop",
    "amendment_loop",
    "checkpoint_loop",
}

REQUIRED_LOOP_KEYS = {
    "scope",
    "paths",
    "entry_condition",
    "convergence_metric",
    "exit_condition",
    "max_iterations",
    "per_iteration_artifact",
    "stagnation_rule",
    "escalation_target",
}

LOOP_TEXT_KEYS = (
    "entry_condition",
    "convergence_metric",
    "exit_condition",
    "per_iteration_artifact",
    "stagnation_rule",
)

LOOP_SCOPES = {"graph", "supervision"}

REQUIRED_TERMINAL_STATES = {"PASSED", "REJECTED"}

REQUIRED_GRAPH_INVARIANTS = {
    "require_all_states_reachable",
    "require_terminal_reachable_from_all",
    "require_terminal_states_are_sinks",
    "require_every_cycle_declared",
    "require_edge_guards",
}

REQUIRED_EDGE_KEYS = {"guard", "required_evidence"}

ENTRY_STATE = "NEW"


class YamlParseError(ValueError):
    pass


class StrictYAMLParser:
    """Parse the small YAML subset used by this repo."""

    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.index = 0

    def parse(self) -> Any:
        value = self._parse_block(0)
        self._skip_ignorable()
        if self.index < len(self.lines):
            line = self.lines[self.index]
            raise YamlParseError(f"unexpected trailing content: {line!r}")
        return value

    def _skip_ignorable(self) -> None:
        while self.index < len(self.lines):
            stripped = self.lines[self.index].strip()
            if not stripped or stripped.startswith("#"):
                self.index += 1
            else:
                break

    def _indent(self, line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def _next_content_indent(self) -> int | None:
        probe = self.index
        while probe < len(self.lines):
            stripped = self.lines[probe].strip()
            if not stripped or stripped.startswith("#"):
                probe += 1
                continue
            return self._indent(self.lines[probe])
        return None

    def _parse_block(self, indent: int) -> Any:
        self._skip_ignorable()
        if self.index >= len(self.lines):
            return {}
        line = self.lines[self.index]
        if self._indent(line) < indent:
            return {}
        if line.strip().startswith("- "):
            return self._parse_list(indent)
        return self._parse_mapping(indent)

    def _parse_mapping(self, indent: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while True:
            self._skip_ignorable()
            if self.index >= len(self.lines):
                break
            line = self.lines[self.index]
            line_indent = self._indent(line)
            stripped = line.strip()
            if line_indent < indent:
                break
            if line_indent > indent:
                raise YamlParseError(f"unexpected indentation near: {line!r}")
            if stripped.startswith("- "):
                break
            if ":" not in stripped:
                raise YamlParseError(f"expected key/value pair near: {line!r}")
            key, raw_value = stripped.split(":", 1)
            key = key.strip()
            raw_value = raw_value.strip()
            self.index += 1
            if not raw_value:
                next_indent = self._next_content_indent()
                if next_indent is None or next_indent <= indent:
                    result[key] = None
                else:
                    result[key] = self._parse_block(next_indent)
            else:
                result[key] = self._parse_scalar(raw_value)
        return result

    def _parse_list(self, indent: int) -> list[Any]:
        result: list[Any] = []
        while True:
            self._skip_ignorable()
            if self.index >= len(self.lines):
                break
            line = self.lines[self.index]
            line_indent = self._indent(line)
            stripped = line.strip()
            if line_indent < indent:
                break
            if not stripped.startswith("- "):
                break
            item = stripped[2:].strip()
            self.index += 1
            if not item:
                next_indent = self._next_content_indent()
                if next_indent is None or next_indent <= indent:
                    result.append(None)
                else:
                    result.append(self._parse_block(next_indent))
            else:
                result.append(self._parse_scalar(item))
        return result

    def _parse_scalar(self, raw: str) -> Any:
        if raw in {"true", "false"}:
            return raw == "true"
        if raw in {"null", "~"}:
            return None
        if re.fullmatch(r"-?\d+", raw):
            return int(raw)
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if not inner:
                return []
            return [self._parse_scalar(part.strip()) for part in inner.split(",")]
        if (raw.startswith('"') and raw.endswith('"')) or (
            raw.startswith("'") and raw.endswith("'")
        ):
            return raw[1:-1]
        return raw


def load_document(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yaml", ".yml", ""}:
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError:
            return StrictYAMLParser(text).parse()
        return yaml.safe_load(text)
    raise ValueError(f"unsupported config format: {path.suffix}")


def as_mapping(value: Any, label: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{label} must be a mapping")
        return {}
    return value


def as_list(value: Any, label: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return []
    return value


def normalize_cycle(states: list[str]) -> tuple[str, ...]:
    """Rotate a cycle so it starts at its lexicographically smallest state."""
    if not states:
        return ()
    offset = states.index(min(states))
    return tuple(states[offset:] + states[:offset])


def reachable_from(start: str, edges: dict[str, list[str]]) -> set[str]:
    seen = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for target in edges.get(node, []):
            if target not in seen:
                seen.add(target)
                stack.append(target)
    return seen


def reverse_edges(edges: dict[str, list[str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for source, targets in edges.items():
        for target in targets:
            result.setdefault(target, []).append(source)
    return result


def find_simple_cycles(edges: dict[str, list[str]]) -> set[tuple[str, ...]]:
    """Enumerate every simple cycle, each rotated to a canonical start state.

    Each cycle is only discovered from its smallest member, so the recorded
    path is already in normalized form.
    """
    nodes = set(edges)
    for targets in edges.values():
        nodes.update(targets)
    cycles: set[tuple[str, ...]] = set()

    def walk(start: str, node: str, path: list[str], seen: set[str]) -> None:
        for target in edges.get(node, []):
            if target == start:
                cycles.add(tuple(path))
            elif target not in seen and target > start:
                walk(start, target, path + [target], seen | {target})

    for start in sorted(nodes):
        walk(start, start, [start], {start})
    return cycles


def validate_loops(
    doc: dict[str, Any],
    state_set: set[str],
    transition_map: dict[str, list[str]],
    errors: list[str],
) -> set[tuple[str, ...]]:
    """Check loop declarations and return the cycles they cover."""
    declared_cycles: set[tuple[str, ...]] = set()
    loops = as_mapping(doc.get("loops"), "loops", errors)
    if not loops:
        return declared_cycles

    missing_loops = sorted(REQUIRED_LOOP_NAMES - set(loops.keys()))
    if missing_loops:
        errors.append(f"loops missing: {', '.join(missing_loops)}")

    for name in sorted(set(loops.keys()) & REQUIRED_LOOP_NAMES):
        loop = as_mapping(loops.get(name), f"loops.{name}", errors)
        if not loop:
            continue
        missing_keys = sorted(REQUIRED_LOOP_KEYS - set(loop.keys()))
        if missing_keys:
            errors.append(f"loops.{name} missing keys: {', '.join(missing_keys)}")

        max_iterations = loop.get("max_iterations")
        if not isinstance(max_iterations, int) or max_iterations < 1:
            errors.append(f"loops.{name}.max_iterations must be a positive integer")
        for key in LOOP_TEXT_KEYS:
            value = loop.get(key)
            if not isinstance(value, str) or not value:
                errors.append(f"loops.{name}.{key} must be a non-empty string")
        if loop.get("escalation_target") not in state_set:
            errors.append(f"loops.{name}.escalation_target must be a declared state")

        scope = loop.get("scope")
        if scope not in LOOP_SCOPES:
            errors.append(f"loops.{name}.scope must be 'graph' or 'supervision'")
        paths = as_list(loop.get("paths"), f"loops.{name}.paths", errors)
        if scope == "supervision":
            if paths:
                errors.append(f"loops.{name} has supervision scope and must declare no paths")
            continue
        if not paths:
            errors.append(f"loops.{name}.paths must not be empty")

        for position, path in enumerate(paths):
            label = f"loops.{name}.paths[{position}]"
            if not isinstance(path, list) or not path:
                errors.append(f"{label} must be a non-empty list")
                continue
            steps = [str(item) for item in path]
            if len(set(steps)) != len(steps):
                errors.append(f"{label} must not repeat a state")
                continue
            unknown = sorted(set(steps) - state_set)
            if unknown:
                errors.append(f"{label} has unknown states: {', '.join(unknown)}")
                continue
            closed = True
            for index, source in enumerate(steps):
                target = steps[(index + 1) % len(steps)]
                if target not in transition_map.get(source, []):
                    errors.append(f"{label} uses an undeclared transition: {source} -> {target}")
                    closed = False
            if closed:
                declared_cycles.add(normalize_cycle(steps))

    return declared_cycles


def validate_graph(
    doc: dict[str, Any],
    state_set: set[str],
    transition_map: dict[str, list[str]],
    declared_cycles: set[tuple[str, ...]],
    errors: list[str],
) -> None:
    graph = as_mapping(doc.get("graph"), "graph", errors)
    if not graph:
        return

    terminal_states = as_list(graph.get("terminal_states"), "graph.terminal_states", errors)
    terminal_set = {str(item) for item in terminal_states}
    missing_terminals = sorted(REQUIRED_TERMINAL_STATES - terminal_set)
    if missing_terminals:
        errors.append(f"graph.terminal_states missing: {', '.join(missing_terminals)}")

    invariants = as_mapping(graph.get("invariants"), "graph.invariants", errors)
    for invariant in sorted(REQUIRED_GRAPH_INVARIANTS):
        if invariants.get(invariant) is not True:
            errors.append(f"graph.invariants.{invariant} must be true")

    edges = as_mapping(graph.get("edges"), "graph.edges", errors)
    declared_edges: set[tuple[str, str]] = set()
    for source in sorted(edges):
        targets = as_mapping(edges.get(source), f"graph.edges.{source}", errors)
        for target in sorted(targets):
            declared_edges.add((source, target))
            edge = as_mapping(targets.get(target), f"graph.edges.{source}.{target}", errors)
            if not edge:
                continue
            for key in sorted(REQUIRED_EDGE_KEYS):
                value = edge.get(key)
                if not isinstance(value, str) or not value:
                    errors.append(
                        f"graph.edges.{source}.{target}.{key} must be a non-empty string"
                    )

    workflow_edges = {
        (source, target)
        for source, targets in transition_map.items()
        for target in targets
    }
    for source, target in sorted(workflow_edges - declared_edges):
        errors.append(f"graph.edges missing: {source} -> {target}")
    for source, target in sorted(declared_edges - workflow_edges):
        errors.append(f"graph.edges declares an undeclared transition: {source} -> {target}")

    for state in sorted(terminal_set):
        if transition_map.get(state):
            errors.append(f"graph terminal state must be a sink: {state}")

    if not state_set or not transition_map:
        return

    unreachable = sorted(state_set - reachable_from(ENTRY_STATE, transition_map))
    if unreachable:
        errors.append(f"states unreachable from {ENTRY_STATE}: {', '.join(unreachable)}")

    backwards = reverse_edges(transition_map)
    can_finish: set[str] = set()
    for terminal in sorted(terminal_set):
        can_finish |= reachable_from(terminal, backwards)
    stuck = sorted(state_set - can_finish)
    if stuck:
        errors.append(f"states with no path to a terminal state: {', '.join(stuck)}")

    for cycle in sorted(find_simple_cycles(transition_map) - declared_cycles):
        route = " -> ".join(cycle + (cycle[0],))
        errors.append(f"undeclared cycle in workflow graph: {route}")


def validate_config(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if doc.get("version") != 1:
        errors.append("version must be 1")

    constitution = as_mapping(doc.get("constitution"), "constitution", errors)
    if constitution:
        if constitution.get("require_harness_before_judgment") is not True:
            errors.append("constitution.require_harness_before_judgment must be true")
        max_rework_count = constitution.get("max_rework_count")
        if not isinstance(max_rework_count, int) or max_rework_count < 1:
            errors.append("constitution.max_rework_count must be a positive integer")
        if constitution.get("allow_judiciary_law_amendment_request") is not True:
            errors.append(
                "constitution.allow_judiciary_law_amendment_request must be true"
            )
        if constitution.get("allow_executive_clarification_request") is not True:
            errors.append(
                "constitution.allow_executive_clarification_request must be true"
            )

    long_task = as_mapping(doc.get("long_task"), "long_task", errors)
    if long_task:
        missing_long_task_keys = sorted(REQUIRED_LONG_TASK_KEYS - set(long_task.keys()))
        if missing_long_task_keys:
            errors.append(
                f"long_task missing keys: {', '.join(missing_long_task_keys)}"
            )
        if long_task.get("enabled") is not True:
            errors.append("long_task.enabled must be true")
        if long_task.get("require_periodic_checkpoints") is not True:
            errors.append(
                "long_task.require_periodic_checkpoints must be true"
            )
        interval = long_task.get("checkpoint_interval_minutes")
        grace = long_task.get("checkpoint_grace_minutes")
        missed = long_task.get("max_missed_checkpoints")
        if not isinstance(interval, int) or interval < 1:
            errors.append(
                "long_task.checkpoint_interval_minutes must be a positive integer"
            )
        if not isinstance(grace, int) or grace < 0:
            errors.append(
                "long_task.checkpoint_grace_minutes must be a non-negative integer"
            )
        if not isinstance(missed, int) or missed < 1:
            errors.append(
                "long_task.max_missed_checkpoints must be a positive integer"
            )
        if long_task.get("escalation_on_miss") != "LAW_CLARIFICATION_REQUEST":
            errors.append(
                "long_task.escalation_on_miss must be LAW_CLARIFICATION_REQUEST"
            )
        summary = long_task.get("require_progress_summary")
        if not isinstance(summary, list):
            errors.append(
                "long_task.require_progress_summary must be a list"
            )
        else:
            summary_set = {str(item) for item in summary}
            missing_summary = sorted(REQUIRED_PROGRESS_FIELDS - summary_set)
            if missing_summary:
                errors.append(
                    "long_task.require_progress_summary missing: "
                    + ", ".join(missing_summary)
                )

    role_isolation = as_mapping(doc.get("role_isolation"), "role_isolation", errors)
    for role in ROLE_NAMES:
        role_cfg = as_mapping(role_isolation.get(role), f"role_isolation.{role}", errors)
        if not role_cfg:
            continue
        if role_cfg.get("model") != "separate":
            errors.append(f"role_isolation.{role}.model must be 'separate'")
        prompt_scope = role_cfg.get("prompt_scope")
        if not isinstance(prompt_scope, str) or not prompt_scope:
            errors.append(f"role_isolation.{role}.prompt_scope must be a string")
        may_read = as_list(role_cfg.get("may_read"), f"role_isolation.{role}.may_read", errors)
        may_not_read = as_list(
            role_cfg.get("may_not_read"), f"role_isolation.{role}.may_not_read", errors
        )
        if not may_read:
            errors.append(f"role_isolation.{role}.may_read must not be empty")
        if not may_not_read:
            errors.append(f"role_isolation.{role}.may_not_read must not be empty")

    state_set: set[str] = set()
    transition_map: dict[str, list[str]] = {}

    workflow = as_mapping(doc.get("workflow"), "workflow", errors)
    if workflow:
        states = as_list(workflow.get("states"), "workflow.states", errors)
        transitions = as_mapping(workflow.get("transitions"), "workflow.transitions", errors)
        state_set = {str(item) for item in states}
        for source, targets in transitions.items():
            if isinstance(targets, list):
                transition_map[str(source)] = [str(target) for target in targets]
        missing_states = sorted(REQUIRED_STATES - state_set)
        if missing_states:
            errors.append(f"workflow.states missing: {', '.join(missing_states)}")
        for state, targets in REQUIRED_TRANSITIONS.items():
            actual = transitions.get(state)
            if actual is None:
                errors.append(f"workflow.transitions missing state: {state}")
                continue
            if not isinstance(actual, list):
                errors.append(f"workflow.transitions.{state} must be a list")
                continue
            actual_set = {str(item) for item in actual}
            missing_targets = sorted(targets - actual_set)
            if missing_targets:
                errors.append(
                    f"workflow.transitions.{state} missing: {', '.join(missing_targets)}"
                )

    harness = as_mapping(doc.get("harness"), "harness", errors)
    if harness:
        required_artifacts = as_list(
            harness.get("required_artifacts"), "harness.required_artifacts", errors
        )
        artifact_set = {str(item) for item in required_artifacts}
        missing_artifacts = sorted(REQUIRED_ARTIFACTS - artifact_set)
        if missing_artifacts:
            errors.append(
                f"harness.required_artifacts missing: {', '.join(missing_artifacts)}"
            )
        gate_behavior = as_mapping(harness.get("gate_behavior"), "harness.gate_behavior", errors)
        if gate_behavior:
            if gate_behavior.get("missing_artifacts") != "INCOMPLETE":
                errors.append("harness.gate_behavior.missing_artifacts must be INCOMPLETE")
            if gate_behavior.get("invalid_artifacts") != "REWORK":
                errors.append("harness.gate_behavior.invalid_artifacts must be REWORK")

    declared_cycles = validate_loops(doc, state_set, transition_map, errors)
    validate_graph(doc, state_set, transition_map, declared_cycles, errors)

    # A loop bound that disagrees with the layer it governs is worse than no
    # bound at all, because both numbers look authoritative.
    loops = doc.get("loops")
    if isinstance(loops, dict):
        rework_loop = loops.get("rework_loop")
        if isinstance(rework_loop, dict):
            if rework_loop.get("max_iterations") != constitution.get("max_rework_count"):
                errors.append(
                    "loops.rework_loop.max_iterations must equal "
                    "constitution.max_rework_count"
                )
        checkpoint_loop = loops.get("checkpoint_loop")
        if isinstance(checkpoint_loop, dict):
            if checkpoint_loop.get("max_iterations") != long_task.get("max_missed_checkpoints"):
                errors.append(
                    "loops.checkpoint_loop.max_iterations must equal "
                    "long_task.max_missed_checkpoints"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate governance config")
    parser.add_argument(
        "path",
        nargs="?",
        default="config/governance.yaml",
        help="Path to governance config (supports .yaml, .yml, or .json)",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1

    try:
        doc = load_document(path)
    except Exception as exc:  # pragma: no cover - user-facing diagnostic
        print(f"ERROR: failed to parse {path}: {exc}", file=sys.stderr)
        return 2

    errors = validate_config(doc)
    if errors:
        print(f"FAIL: {path}")
        for error in errors:
            print(f"- {error}")
        return 3

    print(f"PASS: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
