# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A documentation-first specification of a multi-agent AI governance framework
(constitution → legislative → executive → harness gate → judiciary). There is no
application code: the only executable is `scripts/validate_governance.py`.

`docs/cli-api-reference.md` documents an `ai-gov` CLI and a set of HTTP endpoints —
these are a *proposed* surface, not implemented here. Do not assume they exist or
call them.

## Commands

```bash
# Validate the governance contract (this is the repo's real test)
python3 scripts/validate_governance.py config/governance.yaml
python3 scripts/validate_governance.py config/governance.json   # mirror copy, not covered by CI
python3 scripts/validate_governance.py                          # defaults to config/governance.yaml

# Lint all markdown (markdownlint-cli2 is not vendored; npx fetches it)
npx -y markdownlint-cli2 "**/*.md" "!node_modules"
```

Validator exit codes: `0` pass, `1` file not found, `2` parse failure, `3` validation
errors (each error printed as its own bullet line).

`.github/workflows/ci.yml` runs exactly these two jobs, and only on push/PR to `main`
— feature branches get no CI, so run both locally before pushing.

There is no test framework. `TESTS.md` is a manual doc-review matrix (bilingual
coverage, role coverage), not something you can execute. The closest thing to
"running a single test" is pointing the validator at one config file.

## Architecture: one contract, four copies

The governance contract is duplicated across places that nothing automatically keeps
in sync. A change to any of them usually needs the same change in the others:

1. `config/governance.yaml` — source of truth; the only file CI validates.
2. `config/governance.json` — hand-maintained mirror of the YAML. No check compares
   the two; edit both or they silently drift.
3. `scripts/validate_governance.py` — hardcodes the required contract as module-level
   constants (`REQUIRED_STATES`, `REQUIRED_TRANSITIONS`, `REQUIRED_ARTIFACTS`,
   `REQUIRED_LONG_TASK_KEYS`, `REQUIRED_PROGRESS_FIELDS`, `ROLE_NAMES`).
4. Prose that repeats the same state names and artifact names:
   `docs/state-machine.md`, `docs/governance-architecture.md`, `CONSTITUTION.md`,
   `examples/*.md`, `tests/harness_examples.md`.

Validation is **subset-based, not exact**: the config may add states, transitions, and
harness artifacts, but may never drop a required one. Several values are pinned to an
exact literal and will fail CI if merely relaxed — `version == 1`,
`require_harness_before_judgment == true`, `escalation_on_miss == LAW_CLARIFICATION_REQUEST`,
`gate_behavior.missing_artifacts == INCOMPLETE`, `gate_behavior.invalid_artifacts == REWORK`,
`role_isolation.<role>.model == "separate"`. Loosening the config alone is always a CI
failure; the validator constants have to move first.

## The vendored YAML parser constrains config syntax

`validate_governance.py` contains `StrictYAMLParser`, used whenever PyYAML is not
importable — which is the case in CI (`setup-python` with no install step). It parses a
deliberate subset: nested mappings, dash-prefixed block lists, inline `[a, b]` lists, integers,
`true`/`false`, `null`/`~`, single/double-quoted strings, and `#` comments. Anything
outside that (anchors, folded/multi-line scalars, inline `{}` maps, inconsistent
indentation) either raises `YamlParseError` → exit 2, or is silently kept as a bare
string. Keep `config/governance.yaml` inside the subset; if you need richer YAML,
extend the parser in the same commit.

Note the asymmetry: locally PyYAML may be present, so a config that parses on your
machine can still fail in CI. Test parsing the way CI does before pushing.

## Docs conventions

- **Bilingual is mandatory.** Every doc carries an English section and a 繁體中文
  section with matching structure (`CONTRIBUTING.md` and `TESTS.md` both treat this as
  an acceptance criterion). Adding an English-only section is a regression.
- **MD013 (line length) is disabled** in `.markdownlint.json`; every other markdownlint
  default is on. MD024 (`no-duplicate-heading`) applies across the whole file, not just
  siblings — that is why headings are disambiguated as
  `### Example 1 English` / `#### App idea validation, legislative spec` rather than
  repeating `### English`. Follow that pattern in new docs with parallel sections.
- **New docs need two links.** `README.md` ("Repo docs") and `docs/README_INDEX.md`
  maintain overlapping indexes; add the entry to both.
- Artifact IDs follow `LAW-XXXX`, `CASE-XXXX`, `JUDGMENT-XXXX`, `CHECKPOINT-XXXX`.

## Constraints on content changes

`CONSTITUTION.md` is the repo's own subject matter, and `CONTRIBUTING.md` asks that the
separation-of-powers model stay intact. When editing docs, config, or examples, preserve:
role isolation between legislative/executive/judiciary, the harness gate as a hard
precondition for judgment, a capped rework count, and the reverse feedback paths
(judiciary → legislative amendment, executive → legislative clarification).
