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

ROLE_NAMES = {"legislative", "executive", "judiciary"}


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

    workflow = as_mapping(doc.get("workflow"), "workflow", errors)
    if workflow:
        states = as_list(workflow.get("states"), "workflow.states", errors)
        transitions = as_mapping(workflow.get("transitions"), "workflow.transitions", errors)
        state_set = {str(item) for item in states}
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
