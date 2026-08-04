"""The ai-gov command line.

Every write on behalf of a role goes through that role's `may_write` allowlist.
An operator at a terminal is standing in for a role, and should not be able to
do what that role could not — otherwise the CLI is a hole straight through role
isolation.

The one exception is intake. `NEW` declares no acting role, and `user_request`
is deliberately in no role's `may_write`, because the request comes from the
caller rather than from anyone inside the system. `case start` therefore seeds
it directly. Everything after that belongs to a role.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.agency import RoleAgency  # noqa: E402
from runtime.case import Case  # noqa: E402
from runtime.checks import failures as artifact_failures  # noqa: E402
from runtime.executor import CaseRunner, RunStatus  # noqa: E402
from runtime.roles import IsolationError  # noqa: E402
from runtime.session import DEFAULT_CONFIG, GovernanceSession  # noqa: E402
from runtime.supervision import (  # noqa: E402
    CheckpointStatus,
    CheckpointSupervisor,
    SupervisionError,
)

from .store import ConflictError, Store, StoreError  # noqa: E402

# Exit codes are part of the interface: a pipeline should be able to branch on
# the verdict without parsing prose.
EXIT_OK = 0
EXIT_USAGE = 1
EXIT_BLOCKED = 2
EXIT_REJECTED = 3
EXIT_ESCALATED = 4
EXIT_CONFLICT = 5

VERDICT_EXIT = {
    "PASSED": EXIT_OK,
    "REJECTED": EXIT_REJECTED,
}

SUPERVISION_EXIT = {
    CheckpointStatus.DISABLED: EXIT_OK,
    CheckpointStatus.HEALTHY: EXIT_OK,
    CheckpointStatus.OVERDUE: EXIT_BLOCKED,
    CheckpointStatus.STAGNATED: EXIT_ESCALATED,
    CheckpointStatus.ESCALATED: EXIT_ESCALATED,
}


def apply_as(session: GovernanceSession, role_name: str, case: Case, payload: dict[str, Any]) -> list[str]:
    """Write to a case with the authority of one role, and no more."""
    return session.role(role_name).apply_writes(case, payload)


def parse_pairs(values: list[str] | None, label: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for item in values or []:
        if "=" not in item:
            raise ValueError(f"{label} must be NAME=VALUE, got: {item}")
        name, _, value = item.partition("=")
        pairs[name.strip()] = value
    return pairs


# --- commands -------------------------------------------------------------


def cmd_law_create(args, session: GovernanceSession, store: Store) -> int:
    law = store.create_law(args.title, args.metric or [], args.redline or [])
    print(f"created {law['law_id']}: {law['title']}")
    for criterion in law["acceptance_criteria"]:
        print(f"  criterion: {criterion}")
    for red_line in law["red_lines"]:
        print(f"  red line:  {red_line}")
    if not law["acceptance_criteria"]:
        print("  warning: no acceptance criteria, so nothing can be verified")
    return EXIT_OK


def cmd_law_clarify(args, session: GovernanceSession, store: Store) -> int:
    case = store.load_case(args.case)
    written = apply_as(
        session,
        "executive",
        case,
        {
            "facts": {"open_ambiguity_items": case.fact("open_ambiguity_items") + 1},
            "artifacts": {"ambiguity_notes": args.reason},
        },
    )
    store.save_case(case)
    print(f"{case.case_id}: clarification requested, wrote {', '.join(written)}")
    return EXIT_OK


def cmd_case_start(args, session: GovernanceSession, store: Store) -> int:
    law = store.load_law(args.law)
    case = Case(case_id=store.new_case_id())
    case.facts["user_request"] = args.request or args.name
    case.artifacts["user_request"] = args.request or args.name
    apply_as(
        session,
        "legislative",
        case,
        {
            "facts": {"law": law["law_id"]},
            "artifacts": {"acceptance_criteria": "\n".join(law["acceptance_criteria"])},
        },
    )
    case.facts["case_name"] = args.name
    # Nothing can be late before the clock starts.
    CheckpointSupervisor(session.doc).start(case, args.now)
    store.save_case(case)
    print(f"started {case.case_id} under {law['law_id']}: {args.name}")
    return EXIT_OK


def cmd_case_checkpoint(args, session: GovernanceSession, store: Store) -> int:
    case = store.load_case(args.case)
    supervisor = CheckpointSupervisor(session.doc)
    summary = {
        "completed": args.completed,
        "blocked": args.blocked,
        "next_step": args.next_step,
        "eta": args.eta,
    }
    result = supervisor.record(case, summary, args.now)
    apply_as(session, "executive", case, {"artifacts": {"progress_summary": json.dumps(summary)}})
    store.save_case(case)

    print(f"{case.case_id}: {result.status.value} — {result.note}")
    print(f"  checkpoints recorded: {len(case.checkpoints)}")
    if result.status is CheckpointStatus.STAGNATED:
        print("  a repeated report is not progress; the next review will escalate")
    return SUPERVISION_EXIT[result.status]


def cmd_case_supervise(args, session: GovernanceSession, store: Store) -> int:
    case = store.load_case(args.case)
    supervisor = CheckpointSupervisor(session.doc)
    result = supervisor.review(case, args.now)

    print(f"{case.case_id}: {result.status.value} — {result.note}")
    if case.last_checkpoint_at is not None:
        deadline = supervisor.deadline(case)
        print(f"  last checkpoint: {case.last_checkpoint_at:.0f}")
        print(f"  next due by:     {deadline:.0f}")
    print(f"  missed: {case.missed_checkpoints}/{supervisor.max_missed}")

    if result.status is CheckpointStatus.ESCALATED and args.escalate:
        written = supervisor.escalate(case, session, result.note)
        print(f"  escalated with executive authority, wrote {', '.join(written)}")
        print(f"  the case will route toward {supervisor.escalation_target} on its next run")
    store.save_case(case)
    return SUPERVISION_EXIT[result.status]


def cmd_case_list(args, session: GovernanceSession, store: Store) -> int:
    cases = store.list_cases()
    if not cases:
        print("no cases")
        return EXIT_OK
    for case in cases:
        print(f"{case.case_id:<12} {case.state:<26} {case.fact('case_name', '')}")
    return EXIT_OK


def cmd_harness_submit(args, session: GovernanceSession, store: Store) -> int:
    case = store.load_case(args.case)
    artifacts = parse_pairs(args.note, "--note")
    for name, path in parse_pairs(args.artifact, "--artifact").items():
        source = Path(path)
        if not source.exists():
            print(f"ERROR: no such file: {path}", file=sys.stderr)
            return EXIT_USAGE
        artifacts[name] = source.read_text(encoding="utf-8")

    if not artifacts:
        print("ERROR: nothing to submit; pass --artifact NAME=PATH or --note NAME=TEXT", file=sys.stderr)
        return EXIT_USAGE

    written = apply_as(session, "executive", case, {"artifacts": artifacts})
    store.save_case(case)

    harness = session.doc.get("harness", {})
    required = harness.get("required_artifacts", [])
    behavior = harness.get("gate_behavior", {})
    missing = [name for name in required if name not in case.artifacts]
    print(f"{case.case_id}: submitted {', '.join(written)}")
    if missing:
        print(f"  {behavior.get('missing_artifacts', 'INCOMPLETE')}: still missing {', '.join(missing)}")

    # Reported, not refused. An artifact that says nothing is still something
    # the executive submitted, and the record should say so.
    failed = artifact_failures(case.artifacts, harness.get("artifact_checks", {}))
    for name in sorted(failed):
        print(f"  {behavior.get('invalid_artifacts', 'REWORK')}: {name} fails {', '.join(failed[name])}")
    return EXIT_OK


def cmd_judge_amend(args, session: GovernanceSession, store: Store) -> int:
    case = store.load_case(args.case)
    written = apply_as(
        session,
        "judiciary",
        case,
        {
            "facts": {"defective_law_items": case.fact("defective_law_items") + 1},
            "artifacts": {"amendment_reason": args.reason},
        },
    )
    store.save_case(case)
    print(f"{case.case_id}: amendment requested, wrote {', '.join(written)}")
    return EXIT_OK


def cmd_judge_run(args, session: GovernanceSession, store: Store) -> int:
    case = store.load_case(args.case)

    manual_verdict = args.unresolved is not None or args.defective is not None or args.red_line
    if not manual_verdict and not args.with_models:
        print(
            "ERROR: a verdict source is required. Pass --with-models to let the "
            "judiciary model decide, or record one with --unresolved / --defective / "
            "--red-line.\nRunning without either would let the case pass on defaults, "
            "which is a success claimed without evidence.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    if manual_verdict:
        apply_as(
            session,
            "judiciary",
            case,
            {
                "facts": {
                    "unresolved_law_items": args.unresolved or 0,
                    "defective_law_items": args.defective or 0,
                    "red_line_violated": bool(args.red_line),
                }
            },
        )

    agency = RoleAgency(session, session.doc) if args.with_models else None
    runner = CaseRunner(session.doc, agency=agency)
    result = runner.run(case, max_steps=args.max_steps)
    store.save_case(case)

    print(f"{case.case_id}: {result.status.value} at {case.state}")
    print(f"  {result.note}")
    print(f"  trail: {case.trail()}")

    if result.status is RunStatus.BLOCKED:
        return EXIT_BLOCKED
    if result.status is RunStatus.ESCALATED:
        return EXIT_ESCALATED
    return VERDICT_EXIT.get(case.state, EXIT_BLOCKED)


def cmd_judge_show(args, session: GovernanceSession, store: Store) -> int:
    case = store.load_case(args.case_id)
    print(f"{case.case_id}  {case.fact('case_name', '')}")
    print(f"  state:  {case.state}")
    print(f"  law:    {case.fact('law', '-')}")
    print(f"  trail:  {case.trail()}")

    required = session.doc.get("harness", {}).get("required_artifacts", [])
    present = [name for name in required if name in case.artifacts]
    print(f"  harness: {len(present)}/{len(required)} artifacts")
    for name in required:
        if name not in case.artifacts:
            print(f"    [ ] {name}")
        elif name in case.artifact_failures:
            print(f"    [!] {name} — fails {', '.join(case.artifact_failures[name])}")
        else:
            print(f"    [x] {name}")

    if case.loop_iterations:
        print("  loops:")
        for loop, count in sorted(case.loop_iterations.items()):
            bound = session.doc.get("loops", {}).get(loop, {}).get("max_iterations", "?")
            print(f"    {loop}: {count}/{bound}")

    if case.reply_repairs:
        print("  reply repairs:")
        for role, count in sorted(case.reply_repairs.items()):
            print(f"    {role}: {count}")

    verdict_keys = ["unresolved_law_items", "defective_law_items", "red_line_violated"]
    if any(key in case.facts for key in verdict_keys):
        print("  verdict facts:")
        for key in verdict_keys:
            if key in case.facts:
                print(f"    {key}: {case.facts[key]}")

    return VERDICT_EXIT.get(case.state, EXIT_OK)


# --- wiring ---------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-gov", description="Governed multi-agent workflow")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="governance config path")
    parser.add_argument("--store", default=None, help="record directory (default .ai-gov)")
    parser.add_argument(
        "--now",
        type=float,
        default=None,
        help="override the clock, epoch seconds (for replay and testing)",
    )
    subs = parser.add_subparsers(dest="group", required=True)

    law = subs.add_parser("law", help="legislative commands").add_subparsers(
        dest="command", required=True
    )
    create = law.add_parser("create", help="write a law")
    create.add_argument("--title", required=True)
    create.add_argument("--metric", action="append", help="acceptance criterion (repeatable)")
    create.add_argument("--redline", action="append", help="red line (repeatable)")
    create.set_defaults(handler=cmd_law_create)

    clarify = law.add_parser("clarify", help="request clarification of an ambiguous law")
    clarify.add_argument("--case", required=True)
    clarify.add_argument("--reason", required=True)
    clarify.set_defaults(handler=cmd_law_clarify)

    case = subs.add_parser("case", help="executive commands").add_subparsers(
        dest="command", required=True
    )
    start = case.add_parser("start", help="open a case under a law")
    start.add_argument("--law", required=True)
    start.add_argument("--name", required=True)
    start.add_argument("--request", help="the original user request (defaults to --name)")
    start.set_defaults(handler=cmd_case_start)

    listing = case.add_parser("list", help="list cases")
    listing.set_defaults(handler=cmd_case_list)

    checkpoint = case.add_parser("checkpoint", help="report progress on a long-running case")
    checkpoint.add_argument("--case", required=True)
    checkpoint.add_argument("--completed", required=True)
    checkpoint.add_argument("--blocked", required=True)
    checkpoint.add_argument("--next-step", required=True)
    checkpoint.add_argument("--eta", required=True)
    checkpoint.set_defaults(handler=cmd_case_checkpoint)

    supervise = case.add_parser("supervise", help="check whether a case is still reporting")
    supervise.add_argument("--case", required=True)
    supervise.add_argument(
        "--escalate",
        action="store_true",
        help="if over the miss limit, raise the clarification request",
    )
    supervise.set_defaults(handler=cmd_case_supervise)

    harness = subs.add_parser("harness", help="evidence commands").add_subparsers(
        dest="command", required=True
    )
    submit = harness.add_parser("submit", help="attach evidence to a case")
    submit.add_argument("--case", required=True)
    submit.add_argument("--artifact", action="append", metavar="NAME=PATH", help="attach file contents")
    submit.add_argument("--note", action="append", metavar="NAME=TEXT", help="attach inline text")
    submit.set_defaults(handler=cmd_harness_submit)

    judge = subs.add_parser("judge", help="judiciary commands").add_subparsers(
        dest="command", required=True
    )
    run = judge.add_parser("run", help="run the case through the governance graph")
    run.add_argument("--case", required=True)
    run.add_argument("--with-models", action="store_true", help="let the bound models act")
    run.add_argument("--unresolved", type=int, help="record unresolved law items")
    run.add_argument("--defective", type=int, help="record defective law items")
    run.add_argument("--red-line", action="store_true", help="record a red line violation")
    run.add_argument("--max-steps", type=int, default=100)
    run.set_defaults(handler=cmd_judge_run)

    amend = judge.add_parser("amend", help="request a law amendment")
    amend.add_argument("--case", required=True)
    amend.add_argument("--reason", required=True)
    amend.set_defaults(handler=cmd_judge_amend)

    show = judge.add_parser("show", help="show a case and its verdict")
    show.add_argument("case_id")
    show.set_defaults(handler=cmd_judge_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        session = GovernanceSession.from_path(args.config)
    except Exception as exc:
        print(f"ERROR: cannot load governance config: {exc}", file=sys.stderr)
        return EXIT_USAGE

    store = Store(args.store)
    try:
        return args.handler(args, session, store)
    except ConflictError as exc:
        print(f"CONFLICT: {exc}", file=sys.stderr)
        return EXIT_CONFLICT
    except StoreError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except IsolationError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except SupervisionError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE
