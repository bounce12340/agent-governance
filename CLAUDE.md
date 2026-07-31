# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A specification-and-documentation repo for a multi-agent AI governance framework
(separation of powers: legislative / executive / judiciary, plus a harness evidence gate).
There is no application runtime here. The only executable code is
`scripts/validate_governance.py`. The `ai-gov` CLI and the `POST /laws`-style REST endpoints
in `docs/cli-api-reference.md` are a *proposed* surface, not an implementation — do not
assume they exist or try to run them.

## Commands

```bash
# Validate the governance config (defaults to config/governance.yaml if path omitted)
python3 scripts/validate_governance.py config/governance.yaml
python3 scripts/validate_governance.py config/governance.json

# Lint markdown exactly as CI does
npx --yes markdownlint-cli2 "**/*.md" "!node_modules"

# Lint a single file
npx --yes markdownlint-cli2 README.md
```

Validator exit codes: `0` pass, `1` file not found, `2` parse failure, `3` validation errors
(each error printed as a `- <message>` line).

CI (`.github/workflows/ci.yml`) runs two jobs on push/PR to `main`: markdownlint over all
`**/*.md`, and the validator against `config/governance.yaml` only — `config/governance.json`
is **not** covered by CI, so validate it manually after editing.

`TESTS.md` is a manual review matrix (bilingual coverage, role completeness), not an
automated suite. There is no test runner.

## Architecture: where the governance model actually lives

The same model is encoded in several places that must be changed together. Editing one
alone will either break CI or silently desync the docs from the enforced contract:

1. **`config/governance.yaml`** — the machine-readable source of truth CI validates.
2. **`config/governance.json`** — a byte-for-byte-equivalent duplicate of the YAML. Keep in sync.
3. **`scripts/validate_governance.py`** — hardcodes the *required minimums* as module-level
   constants: `REQUIRED_STATES`, `REQUIRED_TRANSITIONS`, `REQUIRED_ARTIFACTS`,
   `REQUIRED_LONG_TASK_KEYS`, `REQUIRED_PROGRESS_FIELDS`, `ROLE_NAMES`. Adding a workflow
   state or harness artifact to the config alone does nothing; the validator only enforces
   what is listed here.
4. **Prose docs** — `docs/state-machine.md` (state list + ASCII diagram),
   `docs/governance-architecture.md` (layer descriptions), `CONSTITUTION.md` (non-negotiable
   rules). These restate the config in both languages.

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
