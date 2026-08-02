"""Let the role that owns a state actually act in it.

This is the seam between the state machine and the models. The executor decides
where a case may go; the agency decides what the case contains when it gets
there. Keeping them apart means the flow can be tested without a model, and a
model can be tested without the flow.
"""

from __future__ import annotations

import json
from typing import Any

from .case import Case
from .roles import RoleSession
from .session import GovernanceSession


class AgencyError(RuntimeError):
    pass


class RoleAgency:
    """Asks the owning role to produce this state's facts and artifacts."""

    def __init__(self, session: GovernanceSession, doc: dict[str, Any] | None = None) -> None:
        self.session = session
        self.doc = doc if doc is not None else session.doc
        self.state_roles: dict[str, str | None] = self.doc.get("state_roles") or {}
        self.required_artifacts: list[str] = list(
            (self.doc.get("harness") or {}).get("required_artifacts") or []
        )

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
        reply = role.ask(available)
        try:
            payload = json.loads(reply)
        except (TypeError, ValueError):
            # An unreadable role reply is an operational failure worth
            # surfacing, not a case that quietly stalls.
            raise AgencyError(
                f"role {role.role} did not return JSON at state {case.state}"
            ) from None
        if not isinstance(payload, dict):
            raise AgencyError(
                f"role {role.role} returned {type(payload).__name__}, expected an object"
            )
        return role.apply_writes(case, payload)
