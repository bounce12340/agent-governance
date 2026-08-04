"""An HTTP surface for the governance flow, shipped as a WSGI application.

This module exports `create_app()` and nothing that listens on a socket. A
framework would have to be vendored or depended on, and a bundled production
server would be a second thing to keep secure — neither belongs in a repo whose
whole point is that the governance rules are auditable. WSGI is already in the
standard library, and whoever deploys this already runs gunicorn, uWSGI or
waitress.

The HTTP layer adds exactly one thing the CLI did not need: authentication.
A terminal user has already crossed a filesystem boundary to reach the store;
a network client has crossed nothing. So every request names an operator via a
bearer token, and an operator may only act as the roles `operators.<name>.
may_act_as` lists. Beyond that the endpoints are thin — they load a case, write
through the same role authority the CLI uses, and save. No governance decision
lives here.

One rule is worth stating on its own, because it is the difference between a
governance API and a rubber stamp: **`POST /judgments` does not accept a
verdict.** A client submits the facts a verdict is derived from; the server
runs the executor and reports what the graph decided. An endpoint that let the
caller post `result: "PASSED"` would make every guard, loop bound and evidence
requirement in this repo decorative.
"""

from __future__ import annotations

import json
import re
import sys
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.agency import RoleAgency  # noqa: E402
from runtime.case import Case  # noqa: E402
from runtime.checks import failures as artifact_failures  # noqa: E402
from runtime.executor import CaseRunner, ExecutionError, RunStatus  # noqa: E402
from runtime.operators import AuthError, OperatorRegistry  # noqa: E402
from runtime.roles import IsolationError  # noqa: E402
from runtime.session import DEFAULT_CONFIG, GovernanceSession  # noqa: E402
from runtime.supervision import CheckpointSupervisor, SupervisionError  # noqa: E402

from .store import ConflictError, Store, StoreError  # noqa: E402

# A body large enough to exhaust memory is a denial of service that needs no
# credentials, so the limit is applied before the body is read.
MAX_BODY_BYTES = 1_048_576

CASE_PATH = re.compile(r"^/cases/(?P<case_id>[A-Za-z0-9_-]+)$")

# The verdict a client is never allowed to state. Named here rather than
# inline so the refusal and the documentation cannot drift apart.
VERDICT_FIELD = "result"

VERDICT_FACTS = ("unresolved_law_items", "defective_law_items", "red_line_violated")


class HttpError(Exception):
    """A response the handler wants to return instead of a result."""

    def __init__(self, status: int, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra


# --- request helpers -------------------------------------------------------


def read_json_body(environ: dict[str, Any]) -> dict[str, Any]:
    raw_length = environ.get("CONTENT_LENGTH") or "0"
    try:
        length = int(raw_length)
    except ValueError:
        raise HttpError(HTTPStatus.BAD_REQUEST, f"Content-Length is not a number: {raw_length}")
    if length < 0:
        raise HttpError(HTTPStatus.BAD_REQUEST, "Content-Length is negative")
    if length > MAX_BODY_BYTES:
        raise HttpError(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            f"body is {length} bytes, over the {MAX_BODY_BYTES} byte limit",
        )
    raw = environ["wsgi.input"].read(length) if length else b""
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HttpError(HTTPStatus.BAD_REQUEST, f"body is not valid JSON: {exc}")
    if not isinstance(payload, dict):
        raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, "body must be a JSON object")
    return payload


def required_str(body: dict[str, Any], field: str) -> str:
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, f"{field} is required and must be a non-empty string")
    return value


def string_list(body: dict[str, Any], field: str) -> list[str]:
    value = body.get(field) or []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, f"{field} must be a list of strings")
    return [item for item in value if item.strip()]


# --- the application -------------------------------------------------------


class GovernanceApp:
    """WSGI application over one governance config and one record store."""

    def __init__(self, session: GovernanceSession, store: Store) -> None:
        self.session = session
        self.store = store
        self.operators = OperatorRegistry(session.doc)
        self.routes: dict[tuple[str, str], Callable[..., tuple[int, dict[str, Any]]]] = {
            ("POST", "/laws"): self.post_laws,
            ("POST", "/cases"): self.post_cases,
            ("POST", "/harnesses"): self.post_harnesses,
            ("POST", "/judgments"): self.post_judgments,
            ("POST", "/law-amendments"): self.post_law_amendments,
            ("POST", "/law-clarifications"): self.post_law_clarifications,
        }

    # --- authentication ----------------------------------------------------

    def authenticate(self, environ: dict[str, Any]):
        header = environ.get("HTTP_AUTHORIZATION", "")
        scheme, _, presented = header.partition(" ")
        if scheme.lower() != "bearer" or not presented.strip():
            raise HttpError(HTTPStatus.UNAUTHORIZED, "an Authorization: Bearer <token> header is required")
        operator = self.operators.authenticate(presented.strip())
        if operator is None:
            # Deliberately the same message whether the token was unknown or
            # merely belonged to an operator whose variable is unset. Telling
            # the caller which one would turn this endpoint into an oracle for
            # guessing tokens.
            raise HttpError(HTTPStatus.UNAUTHORIZED, "no operator matched the presented token")
        return operator

    def acting_as(self, environ: dict[str, Any], role: str):
        operator = self.authenticate(environ)
        try:
            self.operators.authorise(operator, role)
        except AuthError as exc:
            raise HttpError(HTTPStatus.FORBIDDEN, str(exc))
        return operator

    # --- handlers ----------------------------------------------------------

    def post_laws(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        operator = self.acting_as(environ, "legislative")
        body = read_json_body(environ)
        title = required_str(body, "title")
        criteria = string_list(body, "acceptance_criteria")
        red_lines = string_list(body, "red_lines")

        law = self.store.create_law(title, criteria, red_lines)
        summary = f"{law['law_id']} created by {operator.name}"
        if not criteria:
            # Accepted, but the record should not pretend it is verifiable.
            summary += "; no acceptance criteria, so nothing about it can be verified"
        return HTTPStatus.CREATED, {
            "id": law["law_id"],
            "status": "created",
            "summary": summary,
            "acceptance_criteria": law["acceptance_criteria"],
            "red_lines": law["red_lines"],
        }

    def post_cases(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.acting_as(environ, "legislative")
        body = read_json_body(environ)
        law_id = required_str(body, "law_id")
        name = required_str(body, "name")
        request_text = body.get("request") or name
        if not isinstance(request_text, str):
            raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, "request must be a string")

        law = self.load_law(law_id)
        case = Case(case_id=self.store.new_case_id())
        # Intake, not a role's write. `NEW` declares no acting role and
        # `user_request` is in no role's `may_write`, because the request comes
        # from the caller rather than from anyone inside the system.
        case.facts["user_request"] = request_text
        case.artifacts["user_request"] = request_text
        self.write_as(
            "legislative",
            case,
            {
                "facts": {"law": law["law_id"]},
                "artifacts": {"acceptance_criteria": "\n".join(law["acceptance_criteria"])},
            },
        )
        case.facts["case_name"] = name
        CheckpointSupervisor(self.session.doc).start(case, None)
        self.save(case)
        return HTTPStatus.CREATED, {
            "id": case.case_id,
            "status": case.state,
            "summary": f"{case.case_id} opened under {law['law_id']}: {name}",
        }

    def post_harnesses(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.acting_as(environ, "executive")
        body = read_json_body(environ)
        case_id = required_str(body, "case_id")
        artifacts = body.get("artifacts")
        if not isinstance(artifacts, dict) or not artifacts:
            raise HttpError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "artifacts must be a non-empty object of name -> text",
            )
        if any(not isinstance(value, str) for value in artifacts.values()):
            raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, "every artifact value must be a string")

        case = self.load_case(case_id)
        written = self.write_as("executive", case, {"artifacts": artifacts})
        self.save(case)

        harness = self.session.doc.get("harness", {})
        behavior = harness.get("gate_behavior", {})
        missing = [name for name in harness.get("required_artifacts", []) if name not in case.artifacts]
        failed = artifact_failures(case.artifacts, harness.get("artifact_checks", {}))

        # Reported, not refused. An artifact that says nothing is still
        # something the executive submitted, and the record should say so.
        return HTTPStatus.OK, {
            "id": case.case_id,
            "status": case.state,
            "summary": f"submitted {', '.join(written)}",
            "written": written,
            "missing": sorted(missing),
            "missing_verdict": behavior.get("missing_artifacts", "INCOMPLETE") if missing else None,
            "invalid": {name: failed[name] for name in sorted(failed)},
            "invalid_verdict": behavior.get("invalid_artifacts", "REWORK") if failed else None,
        }

    def post_judgments(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.acting_as(environ, "judiciary")
        body = read_json_body(environ)
        case_id = required_str(body, "case_id")

        if VERDICT_FIELD in body:
            raise HttpError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                f"{VERDICT_FIELD} is not accepted: a judgment is a request, not an assertion. "
                "Submit the facts the verdict is derived from and the server will run the "
                "graph; a caller-supplied verdict would make every guard and evidence "
                "requirement decorative.",
            )

        with_models = bool(body.get("with_models"))
        supplied = {key: body[key] for key in VERDICT_FACTS if key in body}
        if not supplied and not with_models:
            raise HttpError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "a verdict source is required: set with_models, or record findings with "
                f"{', '.join(VERDICT_FACTS)}. Running with neither would let the case reach "
                "PASSED on default values, which is a success claimed without evidence.",
            )

        case = self.load_case(case_id)
        if supplied:
            facts: dict[str, Any] = {}
            for key in ("unresolved_law_items", "defective_law_items"):
                if key in supplied:
                    value = supplied[key]
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        raise HttpError(
                            HTTPStatus.UNPROCESSABLE_ENTITY,
                            f"{key} must be a non-negative integer",
                        )
                    facts[key] = value
            if "red_line_violated" in supplied:
                if not isinstance(supplied["red_line_violated"], bool):
                    raise HttpError(
                        HTTPStatus.UNPROCESSABLE_ENTITY, "red_line_violated must be true or false"
                    )
                facts["red_line_violated"] = supplied["red_line_violated"]
            # Absent findings are zero rather than unknown, exactly as the CLI
            # records them: a fact the judiciary did not raise is a fact it did
            # not find.
            for key in VERDICT_FACTS:
                facts.setdefault(key, False if key == "red_line_violated" else 0)
            self.write_as("judiciary", case, {"facts": facts})

        max_steps = body.get("max_steps", 100)
        if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
            raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, "max_steps must be a positive integer")

        agency = RoleAgency(self.session, self.session.doc) if with_models else None
        try:
            result = CaseRunner(self.session.doc, agency=agency).run(case, max_steps=max_steps)
        except ExecutionError as exc:
            # The graph refused to route. That is a governance defect in the
            # config, not a bad request, so it is reported as a server fault
            # rather than blamed on the caller.
            self.save(case)
            raise HttpError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc), id=case.case_id)
        self.save(case)

        # A REJECTED verdict is a successful request. The verdict lives in the
        # body; using an HTTP error for it would conflate "the system refused
        # to answer" with "the system answered no".
        return HTTPStatus.OK, {
            "id": case.case_id,
            "status": case.state,
            "summary": result.note,
            "run_status": result.status.value,
            "trail": case.trail(),
            "escalated": result.status is RunStatus.ESCALATED,
            "blocked": result.status is RunStatus.BLOCKED,
        }

    def post_law_amendments(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.acting_as(environ, "judiciary")
        body = read_json_body(environ)
        case_id = required_str(body, "case_id")
        reason = required_str(body, "reason")
        proposed = string_list(body, "proposed_changes")
        if proposed:
            # Folded into the reason rather than written as its own key: the
            # judiciary's `may_write` does not include a proposed-changes
            # artifact, and inventing one here would widen judiciary authority
            # from the HTTP layer.
            reason = reason + "\n\nProposed changes:\n" + "\n".join(f"- {item}" for item in proposed)

        case = self.load_case(case_id)
        written = self.write_as(
            "judiciary",
            case,
            {
                "facts": {"defective_law_items": case.fact("defective_law_items") + 1},
                "artifacts": {"amendment_reason": reason},
            },
        )
        self.save(case)
        return HTTPStatus.OK, {
            "id": case.case_id,
            "status": case.state,
            "summary": f"amendment requested, wrote {', '.join(written)}",
            "written": written,
            "defective_law_items": case.fact("defective_law_items"),
        }

    def post_law_clarifications(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.acting_as(environ, "executive")
        body = read_json_body(environ)
        case_id = required_str(body, "case_id")
        reason = required_str(body, "reason")
        notes = body.get("ambiguity_notes") or reason
        if not isinstance(notes, str):
            raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, "ambiguity_notes must be a string")

        case = self.load_case(case_id)
        written = self.write_as(
            "executive",
            case,
            {
                "facts": {"open_ambiguity_items": case.fact("open_ambiguity_items") + 1},
                "artifacts": {"ambiguity_notes": notes},
            },
        )
        self.save(case)
        return HTTPStatus.OK, {
            "id": case.case_id,
            "status": case.state,
            "summary": f"clarification requested, wrote {', '.join(written)}",
            "written": written,
            "open_ambiguity_items": case.fact("open_ambiguity_items"),
        }

    def get_case(self, environ: dict[str, Any], case_id: str) -> tuple[int, dict[str, Any]]:
        # Any authenticated operator may read the record. What comes back is
        # the audit view — state, route, which artifacts exist and whether they
        # pass their checks — and never an artifact's contents. Handing back
        # evidence text would need a role-scoped read, and this layer knows the
        # operator, not which role is asking.
        self.authenticate(environ)
        case = self.load_case(case_id)
        required = self.session.doc.get("harness", {}).get("required_artifacts", [])

        harness = []
        for name in required:
            if name not in case.artifacts:
                harness.append({"artifact": name, "state": "missing"})
            elif name in case.artifact_failures:
                harness.append(
                    {"artifact": name, "state": "invalid", "fails": case.artifact_failures[name]}
                )
            else:
                harness.append({"artifact": name, "state": "present"})

        loops = {
            name: {"iterations": count, "max": self.session.doc.get("loops", {}).get(name, {}).get("max_iterations")}
            for name, count in sorted(case.loop_iterations.items())
        }
        return HTTPStatus.OK, {
            "id": case.case_id,
            "status": case.state,
            "summary": f"{case.fact('case_name', case.case_id)} at {case.state}",
            "law": case.fact("law", None),
            "trail": case.trail(),
            "version": case.version,
            "harness": harness,
            "loops": loops,
            "reply_repairs": case.reply_repairs,
            "checkpoints": len(case.checkpoints),
            "missed_checkpoints": case.missed_checkpoints,
            "verdict_facts": {key: case.facts[key] for key in VERDICT_FACTS if key in case.facts},
        }

    # --- shared plumbing ---------------------------------------------------

    def load_case(self, case_id: str) -> Case:
        try:
            return self.store.load_case(case_id)
        except StoreError as exc:
            raise HttpError(HTTPStatus.NOT_FOUND, str(exc))

    def load_law(self, law_id: str) -> dict[str, Any]:
        try:
            return self.store.load_law(law_id)
        except StoreError as exc:
            raise HttpError(HTTPStatus.NOT_FOUND, str(exc))

    def write_as(self, role: str, case: Case, payload: dict[str, Any]) -> list[str]:
        """Write with one role's authority and no more.

        The operator check above says which role a caller may stand in for.
        This says what that role may write. Both are needed: without the first
        anyone could act as the judiciary, and without the second the judiciary
        could write the executive's evidence.
        """
        try:
            return self.session.role(role).apply_writes(case, payload)
        except IsolationError as exc:
            raise HttpError(HTTPStatus.FORBIDDEN, str(exc), id=case.case_id)

    def save(self, case: Case) -> None:
        try:
            self.store.save_case(case)
        except ConflictError as exc:
            raise HttpError(HTTPStatus.CONFLICT, str(exc), id=case.case_id)
        except StoreError as exc:
            raise HttpError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc), id=case.case_id)

    # --- WSGI --------------------------------------------------------------

    def dispatch(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/") or "/"
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")

        handler = self.routes.get((method, path))
        if handler is not None:
            return handler(environ)

        match = CASE_PATH.match(path)
        if match:
            if method == "GET":
                return self.get_case(environ, match.group("case_id"))
            raise HttpError(
                HTTPStatus.METHOD_NOT_ALLOWED, f"{method} is not allowed on {path}", allow="GET"
            )

        allowed = sorted({verb for verb, route_path in self.routes if route_path == path})
        if allowed:
            raise HttpError(
                HTTPStatus.METHOD_NOT_ALLOWED,
                f"{method} is not allowed on {path}",
                allow=", ".join(allowed),
            )
        raise HttpError(HTTPStatus.NOT_FOUND, f"no such endpoint: {path}")

    def __call__(self, environ: dict[str, Any], start_response: Callable) -> Iterable[bytes]:
        try:
            status, payload = self.dispatch(environ)
            headers = []
        except HttpError as exc:
            status = int(exc.status)
            payload = {
                "id": exc.extra.get("id"),
                "status": "error",
                "summary": exc.message,
            }
            headers = []
            if status == HTTPStatus.UNAUTHORIZED:
                headers.append(("WWW-Authenticate", "Bearer"))
            if "allow" in exc.extra:
                headers.append(("Allow", exc.extra["allow"]))
        except SupervisionError as exc:
            status, payload, headers = int(HTTPStatus.UNPROCESSABLE_ENTITY), {
                "id": None,
                "status": "error",
                "summary": str(exc),
            }, []

        body = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            *headers,
        ]
        start_response(f"{int(status)} {HTTPStatus(int(status)).phrase}", headers)
        return [body]


def create_app(
    config_path: Path | str = DEFAULT_CONFIG,
    store_root: Path | str | None = None,
) -> GovernanceApp:
    """Build the WSGI application. Point a real server at the result."""
    return GovernanceApp(GovernanceSession.from_path(config_path), Store(store_root))


def serve_for_development(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run the app on `wsgiref.simple_server`, which is for development only.

    `wsgiref` is single-threaded, has no timeouts, no request limits beyond the
    one this module applies, and no TLS. Every operator token would cross the
    wire in clear text. It exists here so the endpoints can be exercised
    locally without installing anything — not so this can be deployed.
    """
    from wsgiref.simple_server import make_server

    app = create_app()
    print(f"ai-gov HTTP on http://{host}:{port}")
    print("WARNING: wsgiref is a development server. Do not run it in production.")
    print("         It offers no TLS, so bearer tokens would travel in clear text.")
    for row in app.operators.report():
        print(f"  {row['operator']:<12} may act as {row['may_act_as']:<12} credential={row['credential']}")
    make_server(host, port, app).serve_forever()


if __name__ == "__main__":  # pragma: no cover - manual, development only
    serve_for_development()
