"""Dependency-free runtime for the governance framework.

The governance model lives in `config/governance.yaml`. This package reads it
and binds each role to the model interface the config assigns, so swapping a
provider is a config change rather than a code change.
"""

from .adapters import (
    AdapterError,
    AnthropicMessagesAdapter,
    MissingCredential,
    ModelAdapter,
    OpenAIChatCompletionsAdapter,
    StubAdapter,
    build_adapter,
)
from .case import Case
from .executor import (
    CaseRunner,
    ExecutionError,
    NondeterministicRouting,
    RunStatus,
    StepResult,
)
from .guards import GUARDS
from .roles import IsolationError, RoleSession
from .session import GovernanceSession

__all__ = [
    "AdapterError",
    "AnthropicMessagesAdapter",
    "Case",
    "CaseRunner",
    "ExecutionError",
    "GUARDS",
    "GovernanceSession",
    "IsolationError",
    "MissingCredential",
    "ModelAdapter",
    "NondeterministicRouting",
    "OpenAIChatCompletionsAdapter",
    "RoleSession",
    "RunStatus",
    "StepResult",
    "StubAdapter",
    "build_adapter",
]
