# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Mostly a specification-and-documentation repo for a multi-agent AI governance framework
(separation of powers: legislative / executive / judiciary, plus a harness evidence gate).

Three things are executable: `scripts/validate_governance.py` (config validator), `runtime/`
(binds roles to model interfaces and executes the state machine), and `ai_gov/` (the
`ai-gov` CLI, run via `./bin/ai-gov` or `python3 -m ai_gov`). Everything else is spec — in
particular the `POST /laws`-style REST endpoints in `docs/cli-api-reference.md` remain a
*proposed* surface with no implementation.

## Commands

```bash
# Validate the governance config (defaults to config/governance.yaml if path omitted)
python3 scripts/validate_governance.py config/governance.yaml
python3 scripts/validate_governance.py config/governance.json

# Runtime tests — offline, no credentials, no dependencies
python3 -m unittest discover -s tests -p 'test_*.py'

# A single test class or method
python3 -m unittest tests.test_runtime.RoleIsolationTest
python3 -m unittest tests.test_runtime.RoleIsolationTest.test_forbidden_material_is_rejected

# Report which model interface is bound to which role (calls no model)
python3 -m runtime

# The CLI, straight from a checkout (no install, no dependencies)
./bin/ai-gov --help
./bin/ai-gov law create --title "T" --metric "M" --redline "R"
./bin/ai-gov judge run --case CASE-001 --unresolved 0

# Lint markdown exactly as CI does
npx --yes markdownlint-cli2 "**/*.md" "!node_modules"

# Lint a single file
npx --yes markdownlint-cli2 README.md
```

Validator exit codes: `0` pass, `1` file not found, `2` parse failure, `3` validation errors
(each error printed as a `- <message>` line). `python3 -m runtime` exits `1` if any
credential is missing. `ai-gov` exit codes: `0` ok/`PASSED`, `1` usage or refused write,
`2` blocked, `3` `REJECTED`, `4` escalated — documented in `docs/cli-api-reference.md`.

CI (`.github/workflows/ci.yml`) runs three jobs on push/PR to `main`: markdownlint over all
`**/*.md`, the validator against both configs, and the runtime tests. The runtime job runs
with no secrets and no network — the `stub` interface exists so it can.

`TESTS.md` is a manual review matrix (bilingual coverage, role completeness), separate from
`tests/test_runtime.py`, `tests/test_executor.py`, `tests/test_agency.py`,
`tests/test_cli.py` and `tests/test_supervision.py`, which are the automated suite.

## Architecture: where the governance model actually lives

The same model is encoded in several places that must be changed together. Editing one
alone will either break CI or silently desync the docs from the enforced contract:

1. **`config/governance.yaml`** — the machine-readable source of truth CI validates.
2. **`config/governance.json`** — a byte-for-byte-equivalent duplicate of the YAML. Keep in sync.
3. **`scripts/validate_governance.py`** — hardcodes the *required minimums* as module-level
   constants: `REQUIRED_STATES`, `REQUIRED_TRANSITIONS`, `REQUIRED_ARTIFACTS`,
   `REQUIRED_LONG_TASK_KEYS`, `REQUIRED_PROGRESS_FIELDS`, `ROLE_NAMES`,
   `REQUIRED_LOOP_NAMES`, `REQUIRED_LOOP_KEYS`, `REQUIRED_GRAPH_INVARIANTS`,
   `REQUIRED_EDGE_KEYS`, `REQUIRED_PROVIDER_KEYS`, `KNOWN_INTERFACES`, `KNOWN_GUARDS`.
   Adding a workflow state or harness artifact to the config alone does nothing; the
   validator only enforces what is listed here.
4. **Prose docs** — `docs/state-machine.md` (state list + ASCII diagram),
   `docs/governance-architecture.md` (layer descriptions), `docs/loop-engineering.md`
   (loop contract + declared loops), `docs/graph-engineering.md` (graph invariants +
   enumerated cycles), `docs/model-interfaces.md` (provider schema + adapter contract),
   `docs/case-execution.md` (executor semantics), `docs/long-task-supervision.md`
   (checkpoint contract), `CONSTITUTION.md` (non-negotiable rules). These restate the
   config in both languages.
5. **`runtime/`** — consumes the config at run time and hardcodes none of the flow. Two
   registries must stay equal to validator constants, each asserted by a test so drift
   fails CI rather than surfacing at run time: `runtime/adapters.py:INTERFACES` mirrors
   `KNOWN_INTERFACES`, and `runtime/guards.py:GUARDS` mirrors `KNOWN_GUARDS`. Adding a
   `graph.edges` entry therefore usually means adding a guard implementation too.

**Changing the state machine touches all of these at once.** Adding a transition can create
a new cycle, and an undeclared cycle is a hard validation error — so a new transition
usually also needs a `loops` entry, a `graph.edges` entry with `guard` and
`required_evidence`, and the cycle list in `docs/graph-engineering.md` updated.

### What the validator enforces

It is a superset check plus literal-value assertions, not a schema validator. The config may
add states/transitions/artifacts, but must contain the required ones, and these exact values
are asserted: `constitution.require_harness_before_judgment: true`,
`allow_judiciary_law_amendment_request: true`, `allow_executive_clarification_request: true`,
`max_rework_count` a positive int, `long_task.enabled: true`,
`long_task.escalation_on_miss: LAW_CLARIFICATION_REQUEST`,
`harness.gate_behavior.missing_artifacts: INCOMPLETE`,
`harness.gate_behavior.invalid_artifacts: REWORK`, and every role in `role_isolation` having
`model: separate` with non-empty `may_read` / `may_not_read`.

It also derives facts from the graph rather than trusting the config: it enumerates every
simple cycle in `workflow.transitions` and fails on any cycle not declared in `loops`,
checks reachability from `NEW` and reverse reachability to a terminal state, requires
`graph.edges` to mirror `workflow.transitions` exactly in both directions, and cross-checks
`loops.rework_loop.max_iterations` against `constitution.max_rework_count` and
`loops.checkpoint_loop.max_iterations` against `long_task.max_missed_checkpoints`, and
`loops.checkpoint_loop.escalation_target` against `long_task.escalation_on_miss`.

For providers it enforces that `api_key_env` looks like an environment variable name rather
than a literal key, that non-`stub` interfaces carry an `http(s)://` `base_url`, and that no
two roles resolve to the same `(interface, base_url, model)` triple — that last one is what
turns `model: separate` from a claim into a constraint, so **at least two distinct model
configurations are required** for any valid config.

It also enforces that `role_isolation.<role>.may_write` sets are disjoint across roles, and
that `state_roles` covers every state with either a declared role or an explicit `null`
(terminal states must be `null`).

These mirror the constitution's structural rules — harness before judgment, capped rework,
role isolation, two-way feedback channels. Loosening one in the config without changing
`CONSTITUTION.md` puts the two out of agreement.

### The vendored YAML parser

`validate_governance.py` ships `StrictYAMLParser`, a hand-written parser for the small YAML
subset this repo uses, so the script runs with zero third-party dependencies. It imports
PyYAML only if already present and falls back to the local parser otherwise. Keep
`config/governance.yaml` inside that subset: plain `key: value` mappings, hyphen-prefixed
block list items,
inline `[a, b]` lists, quoted strings, ints, `true`/`false`, `null`/`~`, and `#` comments.
Anchors, multi-line scalars, nested inline maps, and inconsistent indentation raise
`YamlParseError` (exit code 2).

## Documentation conventions

- **Every document is bilingual**: an English section and a 繁體中文 section, with matching
  structure. New docs and new sections in existing docs must carry both.
- **markdownlint runs with only `MD013` (line length) disabled** (`.markdownlint.json`).
  `MD024` (duplicate headings) is therefore active, which bites constantly in a bilingual
  repo where the same heading naturally recurs. Existing docs disambiguate by suffixing the
  heading — `### Example 1 English` / `### Example 1 繁體中文`,
  `#### POST /laws (English)` / `#### POST /laws (繁體中文)`,
  `#### App idea validation, legislative spec`, `### Added (1.0.0)`. Follow that pattern
  rather than repeating a bare heading.
- Adding a doc under `docs/` means adding it to **both** link indexes:
  `docs/README_INDEX.md` and the "Repo docs / 文件索引" section of `README.md`.
- House style (from `CONTRIBUTING.md`): keep the separation-of-powers model intact, keep
  acceptance criteria testable, keep examples short and concrete, avoid marketing-only text.
