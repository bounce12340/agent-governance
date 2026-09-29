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
    ScriptedAdapter,
    StubAdapter,
    build_adapter,
)
from .agency import AgencyError, RoleAgency
from .case import Case
from .checks import CHECKS
from .convergence import RULES as CONVERGENCE_RULES
from .checks import failures as artifact_failures
from .executor import (
    CaseRunner,
    ExecutionError,
    NondeterministicRouting,
    RunStatus,
    StepResult,
)
from .guards import GUARDS
from .operators import AuthError, Operator, OperatorRegistry
from .roles import IsolationError, RoleSession
from .session import GovernanceSession
from .supervision import (
    CheckpointStatus,
    CheckpointSupervisor,
    SupervisionError,
    SupervisionResult,
)

__all__ = [
    "AdapterError",
    "AgencyError",
    "AuthError",
    "CHECKS",
    "CONVERGENCE_RULES",
    "AnthropicMessagesAdapter",
    "Case",
    "CaseRunner",
    "CheckpointStatus",
    "CheckpointSupervisor",
    "ExecutionError",
    "GUARDS",
    "GovernanceSession",
    "IsolationError",
    "MissingCredential",
    "ModelAdapter",
    "Operator",
    "OperatorRegistry",
    "NondeterministicRouting",
    "OpenAIChatCompletionsAdapter",
    "RoleAgency",
    "RoleSession",
    "RunStatus",
    "ScriptedAdapter",
    "StepResult",
    "StubAdapter",
    "SupervisionError",
    "SupervisionResult",
    "artifact_failures",
    "build_adapter",
]
