"""Build role sessions from the governance config.

The config is the single source of truth for which model interface sits in
which seat. Nothing here hardcodes a vendor.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .adapters import ModelAdapter, build_adapter
from .roles import RoleSession

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "governance.yaml"

# The validator already ships a dependency-free loader for this config, and
# duplicating it here would let the two drift apart.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from validate_governance import load_document  # noqa: E402


class GovernanceSession:
    """Every role, each bound to its own declared model interface."""

    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc
        providers = doc.get("providers") or {}
        role_isolation = doc.get("role_isolation") or {}

        self.adapters: dict[str, ModelAdapter] = {}
        self.roles: dict[str, RoleSession] = {}
        for role, role_cfg in role_isolation.items():
            provider_name = role_cfg.get("provider")
            provider = providers.get(provider_name)
            if provider is None:
                raise KeyError(f"role {role} names undeclared provider: {provider_name}")
            adapter = build_adapter(str(provider_name), provider)
            self.adapters[role] = adapter
            self.roles[role] = RoleSession(
                role=role,
                adapter=adapter,
                prompt_scope=role_cfg.get("prompt_scope", ""),
                may_read=role_cfg.get("may_read") or [],
                may_not_read=role_cfg.get("may_not_read") or [],
                may_write=role_cfg.get("may_write") or [],
            )

    @classmethod
    def from_path(cls, path: Path | str = DEFAULT_CONFIG) -> GovernanceSession:
        return cls(load_document(Path(path)))

    def role(self, name: str) -> RoleSession:
        return self.roles[name]

    def loop_bound(self, loop_name: str) -> int:
        """Iteration ceiling for a declared loop, as the config states it."""
        return int(self.doc["loops"][loop_name]["max_iterations"])

    def report(self) -> list[dict[str, Any]]:
        """Per-role wiring status. Never reads a credential's value."""
        rows = []
        for role in sorted(self.roles):
            adapter = self.adapters[role]
            rows.append(
                {
                    "role": role,
                    "provider": adapter.name,
                    "interface": adapter.interface,
                    "model": adapter.model,
                    "base_url": adapter.base_url or "-",
                    "credential": "set" if adapter.credential_present() else "missing",
                }
            )
        return rows


def main(argv: list[str] | None = None) -> int:
    """`python3 -m runtime` prints the wiring without calling any model."""
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0]) if args else DEFAULT_CONFIG
    session = GovernanceSession.from_path(path)

    print(f"Governance runtime wiring from {path}\n")
    for row in session.report():
        print(f"  {row['role']:<12} {row['provider']:<24} {row['interface']}")
        print(f"  {'':<12} model={row['model']}  endpoint={row['base_url']}")
        print(f"  {'':<12} credential={row['credential']}\n")

    missing = [row["role"] for row in session.report() if row["credential"] == "missing"]
    if missing:
        print(f"Credentials missing for: {', '.join(missing)}")
        return 1
    return 0
