# Changelog

All notable changes to this project will be documented here.

## Unreleased

### Added (Unreleased)

- Bilingual README
- Technical docs for state machine and CLI/API reference
- Example law and harness test files
- Social copy for Threads and Facebook
- Loop engineering layer: named loop contracts with convergence metrics,
  stagnation rules, and iteration bounds for all four loops
- Graph engineering layer: machine-checked graph invariants, guarded edges,
  and cycle enumeration that rejects any undeclared cycle
- Model interface layer: a `providers` config block, per-role provider binding,
  and a dependency-free `runtime/` that speaks the OpenAI chat-completions and
  Anthropic messages interfaces plus an offline stub
- Role isolation is now enforced across models: no two roles may resolve to the
  same interface, endpoint and model
- Case execution layer: a `CaseRunner` that walks the declared graph, applies
  the harness gate, counts loop iterations, detects stagnation, and refuses
  nondeterministic routing when two guards on one fan-out are satisfied
- Guard implementations registry, cross-checked by the validator so an edge
  naming a guard nobody wrote fails validation
- Role agency: `state_roles` binds each state to the role that acts in it, and
  `RoleAgency` turns that role's reply into the case's facts and artifacts
- Write authority: `role_isolation.<role>.may_write` complements `may_read`,
  with disjoint ownership enforced so no role can write another's verdict
- Every declared loop bound is enforced, not just the rework loop's; the graph
  routes the overflow where it can express it, and the loop layer halts the run
  where it cannot
- Artifact validity: `harness.artifact_checks` declares mechanical checks per
  artifact, and the gate marks what fails so `gate_behavior.invalid_artifacts`
  is reachable for the first time
- Long-task supervision is enforced rather than described: derived miss counts,
  required progress-summary fields, stagnation on a repeated report, and
  escalation raised with the executive's own authority
- `ai-gov` CLI implementing the documented command surface, with a flat-file
  record store, verdict-bearing exit codes, and writes bound by the acting
  role's authority
- Offline runtime test suite and a third CI job that runs it without secrets
- `CLAUDE.md` guidance for Claude Code

### Changed

- README rewritten into a cleaner technical-doc style
- Documentation structure expanded

## 1.0.0 - 2026-04-09

### Added (1.0.0)

- Initial public release
- Separation of powers AI governance framework
- Harness engineering concept layer
