"""Let the role that owns a state actually act in it.

This is the seam between the state machine and the models. The executor decides
where a case may go; the agency decides what the case contains when it gets
there. Keeping them apart means the flow can be tested without a model, and a
model can be tested without the flow.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .case import Case
from .roles import RoleSession
from .session import GovernanceSession

FENCED_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class AgencyError(RuntimeError):
    pass


def extract_object(text: str) -> dict[str, Any] | None:
    """Recover a JSON object from a reply that is nearly JSON.

    Models wrap payloads in prose and code fences constantly. Salvaging those
    deterministically costs nothing and spends no model call, so it happens
    before any repair round trip.
    """
    if not isinstance(text, str):
        return None
    stripped = text.strip()

    candidates = [stripped]
    candidates.extend(match.group(1).strip() for match in FENCED_BLOCK.finditer(stripped))
    opening, closing = stripped.find("{"), stripped.rfind("}")
    if 0 <= opening < closing:
        candidates.append(stripped[opening : closing + 1])

    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


class RoleAgency:
    """Asks the owning role to produce this state's facts and artifacts."""

    def __init__(self, session: GovernanceSession, doc: dict[str, Any] | None = None) -> None:
        self.session = session
        self.doc = doc if doc is not None else session.doc
        self.state_roles: dict[str, str | None] = self.doc.get("state_roles") or {}
        self.required_artifacts: list[str] = list(
            (self.doc.get("harness") or {}).get("required_artifacts") or []
        )
        replies = self.doc.get("model_replies") or {}
        # A repair is a retry, so its ceiling is declared rather than assumed.
        # An unbounded repair loop would be the exact failure the loop layer
        # exists to prevent, one level down.
        self.max_repair_attempts = int(replies.get("max_repair_attempts") or 0)

    def owner(self, state: str) -> RoleSession | None:
        role_name = self.state_roles.get(state)
        if not role_name:
            return None
        return self.session.role(role_name)

    def materials(self, case: Case) -> dict[str, Any]:
        """Map case contents into the vocabulary `may_read` is written in.

        Every key here is filtered again by the role's allowlist, so producing
        a superset is safe — `RoleSession.build_context` drops what the role
        may not read and raises on what it must never see.
        """
        harness = {
            name: case.artifacts[name]
            for name in self.required_artifacts
            if name in case.artifacts
        }
        other = {
            name: value
            for name, value in case.artifacts.items()
            if name not in harness
        }
        return {
            "user_request": case.fact("user_request", None),
            "law": case.fact("law", None),
            "constitution": self.doc.get("constitution"),
            "case_artifacts": other,
            "harness_artifacts": harness,
        }

    def act(self, case: Case) -> list[str] | None:
        """Run one role turn. Returns the keys written, or None if nobody acts."""
        role = self.owner(case.state)
        if role is None:
            return None

        available = {k: v for k, v in self.materials(case).items() if v not in (None, {})}
        context = role.build_context(available)
        reply = role.adapter.complete(role.system_prompt(), context)

        payload = extract_object(reply)
        attempts = 0
        while payload is None and attempts < self.max_repair_attempts:
            attempts += 1
            reply = role.adapter.complete(role.system_prompt(), self.repair_prompt(context, reply))
            payload = extract_object(reply)

        if attempts:
            # Worth recording: a role that needs repairing is a fact about the
            # run, and a silent retry would hide a model drifting off format.
            case.reply_repairs[role.role] = case.reply_repairs.get(role.role, 0) + attempts

        if payload is None:
            raise AgencyError(
                f"role {role.role} did not return JSON at state {case.state} "
                f"after {attempts} repair attempt(s)"
            )
        return role.apply_writes(case, payload)

    def repair_prompt(self, context: str, reply: str) -> str:
        """Ask again, showing the role its own unusable answer.

        Only the role's own output is quoted back, so a repair cannot smuggle
        in material the role may not read.
        """
        return (
            "Your previous reply could not be parsed as JSON.\n"
            'Reply again with a JSON object only, shaped {"facts": {...}, "artifacts": {...}}.\n'
            "No prose, no explanation, no code fences.\n\n"
            f"Your previous reply was:\n{reply}\n\n"
            f"The request was:\n{context}"
        )
