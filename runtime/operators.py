"""Who is allowed to act as which role over the network.

The CLI could rely on filesystem access as its authorisation: whoever can run
the binary can already read the store. HTTP has no such boundary, so an
unauthenticated endpoint would let anyone act as any role — which would undo
role isolation more completely than any bug in it.

This is deliberately not a general auth system. There are no users, sessions,
password resets or scopes. There is one question: which roles may this bearer
token act as? Anything larger would be a second security model living beside
the governance one.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass, field
from typing import Any


class AuthError(RuntimeError):
    pass


@dataclass
class Operator:
    name: str
    token_env: str
    roles: list[str] = field(default_factory=list)

    def token(self) -> str | None:
        """The configured token, or None when the variable is unset.

        The value is returned for comparison only. It is never logged, never
        rendered, and never put in an error message — the variable name is
        what identifies the operator in diagnostics.
        """
        return os.environ.get(self.token_env) or None

    def credential_present(self) -> bool:
        return self.token() is not None

    def may_act_as(self, role: str) -> bool:
        return role in self.roles


class OperatorRegistry:
    """Resolves a bearer token to the roles it is allowed to act as."""

    def __init__(self, doc: dict[str, Any]) -> None:
        self.operators: dict[str, Operator] = {}
        for name, cfg in (doc.get("operators") or {}).items():
            if not isinstance(cfg, dict):
                continue
            self.operators[name] = Operator(
                name=name,
                token_env=str(cfg.get("token_env") or ""),
                roles=[str(role) for role in cfg.get("may_act_as") or []],
            )

    def authenticate(self, presented: str | None) -> Operator | None:
        """Match a presented token against every configured operator.

        Every operator is compared, and each comparison is constant-time, so
        neither the number of comparisons nor their duration reveals which
        token was close. Operators whose variable is unset can never match:
        an absent credential must not authenticate as an absent token.
        """
        if not presented:
            return None
        matched: Operator | None = None
        for operator in self.operators.values():
            configured = operator.token()
            if configured is None:
                continue
            if hmac.compare_digest(configured, presented) and matched is None:
                matched = operator
        return matched

    def authorise(self, operator: Operator | None, role: str) -> Operator:
        if operator is None:
            raise AuthError("no operator matched the presented token")
        if not operator.may_act_as(role):
            raise AuthError(f"operator {operator.name} may not act as {role}")
        return operator

    def report(self) -> list[dict[str, Any]]:
        """Wiring status. Reports presence, never a token value."""
        return [
            {
                "operator": name,
                "may_act_as": ", ".join(operator.roles),
                "credential": "set" if operator.credential_present() else "missing",
            }
            for name, operator in sorted(self.operators.items())
        ]
