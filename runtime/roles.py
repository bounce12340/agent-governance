"""Role sessions that enforce isolation at the adapter boundary.

`role_isolation.<role>.may_read` and `may_not_read` are only real if something
filters the context before it reaches a model. That is what this module does:
a role's prompt is assembled from an allowlist, so a forbidden artifact cannot
reach the model even if the caller passes it in.
"""

from __future__ import annotations

from typing import Any

from .adapters import ModelAdapter


class IsolationError(RuntimeError):
    pass


class RoleSession:
    """One governance role bound to one model interface."""

    def __init__(
        self,
        role: str,
        adapter: ModelAdapter,
        prompt_scope: str,
        may_read: list[str],
        may_not_read: list[str],
        may_write: list[str] | None = None,
    ) -> None:
        self.role = role
        self.adapter = adapter
        self.prompt_scope = prompt_scope
        self.may_read = list(may_read)
        self.may_not_read = list(may_not_read)
        self.may_write = list(may_write or [])

        overlap = sorted(set(self.may_read) & set(self.may_not_read))
        if overlap:
            raise IsolationError(
                f"role {role} both may and may not read: {', '.join(overlap)}"
            )

    def system_prompt(self) -> str:
        return (
            f"You are the {self.role} role in a governed multi-agent system.\n"
            f"Prompt scope: {self.prompt_scope}.\n"
            f"You may read: {', '.join(self.may_read)}.\n"
            f"You may never read or infer: {', '.join(self.may_not_read)}.\n"
            f"You may write only these keys: {', '.join(self.may_write)}.\n"
            "Reply with JSON only, shaped "
            '{"facts": {...}, "artifacts": {...}}. '
            "Writing any other key is a governance violation and will be refused.\n"
            "Stay inside your role. Do not perform another role's work."
        )

    def apply_writes(self, case: Any, payload: dict[str, Any]) -> list[str]:
        """Apply a role's declared writes, refusing anything outside its authority.

        Overstepping raises rather than being trimmed. A role reaching for
        another role's key is exactly the failure this framework exists to
        catch, so it should be loud.
        """
        facts = payload.get("facts") or {}
        artifacts = payload.get("artifacts") or {}
        if not isinstance(facts, dict) or not isinstance(artifacts, dict):
            raise IsolationError(f"role {self.role} returned a malformed write payload")

        allowed = set(self.may_write)
        overreach = sorted((set(facts) | set(artifacts)) - allowed)
        if overreach:
            raise IsolationError(
                f"role {self.role} tried to write outside its authority: "
                f"{', '.join(overreach)}"
            )

        case.facts.update(facts)
        case.artifacts.update(artifacts)
        return sorted(set(facts) | set(artifacts))

    def build_context(self, materials: dict[str, Any]) -> str:
        """Assemble a prompt from the allowlist.

        A forbidden artifact is an error rather than a silent drop: passing one
        in means the caller believes this role should see it, and that
        disagreement should surface loudly.
        """
        forbidden = sorted(set(materials) & set(self.may_not_read))
        if forbidden:
            raise IsolationError(
                f"role {self.role} was handed forbidden material: {', '.join(forbidden)}"
            )

        sections = []
        for key in self.may_read:
            if key in materials:
                sections.append(f"## {key}\n{materials[key]}")
        return "\n\n".join(sections)

    def ask(self, materials: dict[str, Any]) -> str:
        return self.adapter.complete(self.system_prompt(), self.build_context(materials))
