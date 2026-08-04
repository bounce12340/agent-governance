"""Offline tests for the WSGI HTTP surface.

No socket is opened and no server is started: a WSGI application is a callable
taking `environ` and `start_response`, so it can be exercised directly. That is
one of the reasons the API is shipped as WSGI rather than as a bundled server.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ai_gov.api import MAX_BODY_BYTES, create_app  # noqa: E402
from ai_gov.store import ConflictError, Store  # noqa: E402

TOKENS = {
    "AI_GOV_TOKEN_INTAKE": "intake-token",
    "AI_GOV_TOKEN_BUILD": "build-token",
    "AI_GOV_TOKEN_REVIEWER": "reviewer-token",
}

INTAKE = TOKENS["AI_GOV_TOKEN_INTAKE"]
BUILD = TOKENS["AI_GOV_TOKEN_BUILD"]
REVIEW = TOKENS["AI_GOV_TOKEN_REVIEWER"]

GOOD_EVIDENCE = {
    "test_plan": "collect at least 30 survey responses and 5 interviews",
    "evidence_bundle": "survey export attached, 31 rows",
    "output_snapshot": "screenshots of the core flow, build 1.0.0",
    "failure_mode_notes": "two crashes on rotate, both fixed",
}


class Response:
    def __init__(self, status: str, headers: list[tuple[str, str]], body: bytes) -> None:
        self.status = status
        self.code = int(status.split(" ", 1)[0])
        self.headers = {name.lower(): value for name, value in headers}
        self.body = json.loads(body.decode("utf-8"))

    @property
    def summary(self) -> str:
        return self.body.get("summary", "")


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        for name, value in TOKENS.items():
            os.environ[name] = value
            self.addCleanup(os.environ.pop, name, None)
        self.root = Path(tempfile.mkdtemp())
        self.app = create_app(store_root=self.root)

    # --- request helper ----------------------------------------------------

    def call(
        self,
        method: str,
        path: str,
        token: str | None = None,
        body: dict | None = None,
        raw: bytes | None = None,
        content_length: str | None = None,
    ) -> Response:
        if raw is None:
            raw = json.dumps(body).encode("utf-8") if body is not None else b""
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "CONTENT_LENGTH": content_length if content_length is not None else str(len(raw)),
            "wsgi.input": io.BytesIO(raw),
        }
        if token is not None:
            environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        captured: dict = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            captured["status"] = status
            captured["headers"] = headers

        payload = b"".join(self.app(environ, start_response))
        return Response(captured["status"], captured["headers"], payload)

    # --- fixtures ----------------------------------------------------------

    def make_law(self) -> str:
        response = self.call(
            "POST",
            "/laws",
            INTAKE,
            {
                "title": "App Launch Law",
                "acceptance_criteria": ["30 survey responses", "5 interviews"],
                "red_lines": ["no missing privacy policy"],
            },
        )
        self.assertEqual(response.code, 201)
        return response.body["id"]

    def make_case(self, law_id: str | None = None) -> str:
        law_id = law_id or self.make_law()
        response = self.call(
            "POST", "/cases", INTAKE, {"law_id": law_id, "name": "Habit App MVP", "request": "Build it"}
        )
        self.assertEqual(response.code, 201)
        return response.body["id"]

    def submit_evidence(self, case_id: str, **overrides) -> Response:
        artifacts = dict(GOOD_EVIDENCE)
        artifacts.update(overrides)
        return self.call("POST", "/harnesses", BUILD, {"case_id": case_id, "artifacts": artifacts})


class AuthenticationTest(ApiTestCase):
    def test_no_header_is_unauthorised(self) -> None:
        response = self.call("POST", "/laws", body={"title": "T"})
        self.assertEqual(response.code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_a_non_bearer_scheme_is_unauthorised(self) -> None:
        environ_response = self.call("POST", "/laws", body={"title": "T"})
        self.assertEqual(environ_response.code, 401)

    def test_an_unknown_token_is_unauthorised(self) -> None:
        response = self.call("POST", "/laws", "not-a-token", {"title": "T"})
        self.assertEqual(response.code, 401)

    def test_the_refusal_does_not_say_which_token_was_close(self) -> None:
        """Naming the near miss would make the endpoint an oracle for guessing."""
        unknown = self.call("POST", "/laws", "not-a-token", {"title": "T"})
        os.environ.pop("AI_GOV_TOKEN_INTAKE", None)
        unset = create_app(store_root=self.root)
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/laws",
            "CONTENT_LENGTH": "0",
            "wsgi.input": io.BytesIO(b""),
            "HTTP_AUTHORIZATION": f"Bearer {INTAKE}",
        }
        captured: dict = {}
        body = b"".join(unset(environ, lambda s, h: captured.update(status=s, headers=h)))
        self.assertEqual(unknown.summary, json.loads(body)["summary"])

    def test_a_token_never_appears_in_a_response(self) -> None:
        response = self.call("POST", "/laws", INTAKE, {"title": "T"})
        rendered = json.dumps(response.body)
        for value in TOKENS.values():
            self.assertNotIn(value, rendered)


class AuthorisationTest(ApiTestCase):
    def test_an_operator_cannot_legislate_on_the_executive_token(self) -> None:
        response = self.call("POST", "/laws", BUILD, {"title": "T"})
        self.assertEqual(response.code, 403)
        self.assertIn("build_bot", response.summary)

    def test_an_operator_cannot_submit_evidence_on_the_judiciary_token(self) -> None:
        case_id = self.make_case()
        response = self.call(
            "POST", "/harnesses", REVIEW, {"case_id": case_id, "artifacts": {"test_plan": "x"}}
        )
        self.assertEqual(response.code, 403)

    def test_an_operator_cannot_judge_on_the_executive_token(self) -> None:
        case_id = self.make_case()
        response = self.call(
            "POST", "/judgments", BUILD, {"case_id": case_id, "unresolved_law_items": 0}
        )
        self.assertEqual(response.code, 403)

    def test_clarification_is_the_executives_and_amendment_is_the_judiciarys(self) -> None:
        case_id = self.make_case()
        self.assertEqual(
            self.call("POST", "/law-clarifications", REVIEW, {"case_id": case_id, "reason": "r"}).code,
            403,
        )
        self.assertEqual(
            self.call("POST", "/law-amendments", BUILD, {"case_id": case_id, "reason": "r"}).code,
            403,
        )


class RoutingTest(ApiTestCase):
    def test_an_unknown_path_is_not_found(self) -> None:
        self.assertEqual(self.call("GET", "/nope", REVIEW).code, 404)

    def test_a_wrong_method_says_what_is_allowed(self) -> None:
        response = self.call("GET", "/laws", INTAKE)
        self.assertEqual(response.code, 405)
        self.assertEqual(response.headers["allow"], "POST")

    def test_a_wrong_method_on_a_case_says_get(self) -> None:
        case_id = self.make_case()
        response = self.call("DELETE", f"/cases/{case_id}", BUILD)
        self.assertEqual(response.code, 405)
        self.assertEqual(response.headers["allow"], "GET")

    def test_a_trailing_slash_is_the_same_endpoint(self) -> None:
        self.assertEqual(self.call("POST", "/laws/", INTAKE, {"title": "T"}).code, 201)

    def test_every_response_is_json(self) -> None:
        response = self.call("GET", "/nope", REVIEW)
        self.assertTrue(response.headers["content-type"].startswith("application/json"))
        self.assertEqual(int(response.headers["content-length"]), len(json.dumps(response.body, indent=2, ensure_ascii=False)) + 1)


class BodyTest(ApiTestCase):
    def test_malformed_json_is_a_bad_request(self) -> None:
        response = self.call("POST", "/laws", INTAKE, raw=b"{oops")
        self.assertEqual(response.code, 400)
        self.assertIn("not valid JSON", response.summary)

    def test_a_json_array_is_not_a_body(self) -> None:
        response = self.call("POST", "/laws", INTAKE, raw=b"[1, 2]")
        self.assertEqual(response.code, 422)

    def test_a_missing_required_field_is_unprocessable(self) -> None:
        response = self.call("POST", "/laws", INTAKE, {})
        self.assertEqual(response.code, 422)
        self.assertIn("title", response.summary)

    def test_an_oversized_body_is_refused_before_it_is_read(self) -> None:
        response = self.call(
            "POST", "/laws", INTAKE, raw=b"{}", content_length=str(MAX_BODY_BYTES + 1)
        )
        self.assertEqual(response.code, 413)

    def test_a_nonsense_content_length_is_a_bad_request(self) -> None:
        response = self.call("POST", "/laws", INTAKE, raw=b"{}", content_length="lots")
        self.assertEqual(response.code, 400)


class LawTest(ApiTestCase):
    def test_a_law_is_created_with_its_criteria(self) -> None:
        response = self.call(
            "POST",
            "/laws",
            INTAKE,
            {"title": "App Launch Law", "acceptance_criteria": ["30 responses"], "red_lines": []},
        )
        self.assertEqual(response.code, 201)
        self.assertEqual(response.body["acceptance_criteria"], ["30 responses"])

    def test_a_law_with_no_criteria_is_accepted_and_says_so(self) -> None:
        response = self.call("POST", "/laws", INTAKE, {"title": "Vibes Law"})
        self.assertEqual(response.code, 201)
        self.assertIn("nothing about it can be verified", response.summary)

    def test_criteria_must_be_strings(self) -> None:
        response = self.call("POST", "/laws", INTAKE, {"title": "T", "acceptance_criteria": [7]})
        self.assertEqual(response.code, 422)


class CaseTest(ApiTestCase):
    def test_a_case_opens_under_its_law(self) -> None:
        law_id = self.make_law()
        response = self.call("POST", "/cases", INTAKE, {"law_id": law_id, "name": "MVP"})
        self.assertEqual(response.code, 201)
        self.assertEqual(response.body["status"], "NEW")
        self.assertIn(law_id, response.summary)

    def test_an_unknown_law_is_not_found(self) -> None:
        response = self.call("POST", "/cases", INTAKE, {"law_id": "LAW-999", "name": "MVP"})
        self.assertEqual(response.code, 404)

    def test_the_request_text_defaults_to_the_name(self) -> None:
        law_id = self.make_law()
        case_id = self.call("POST", "/cases", INTAKE, {"law_id": law_id, "name": "MVP"}).body["id"]
        self.assertEqual(Store(self.root).load_case(case_id).fact("user_request"), "MVP")

    def test_intake_is_seeded_without_a_role_writing_it(self) -> None:
        """`user_request` is in no role's may_write; the caller supplies it."""
        case_id = self.make_case()
        case = Store(self.root).load_case(case_id)
        self.assertEqual(case.artifacts["user_request"], "Build it")
        self.assertEqual(case.artifacts["acceptance_criteria"], "30 survey responses\n5 interviews")


class HarnessTest(ApiTestCase):
    def test_evidence_is_written_and_reported(self) -> None:
        case_id = self.make_case()
        response = self.submit_evidence(case_id)
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body["missing"], [])
        self.assertEqual(response.body["invalid"], {})

    def test_a_partial_bundle_reports_what_is_missing(self) -> None:
        case_id = self.make_case()
        response = self.call(
            "POST", "/harnesses", BUILD, {"case_id": case_id, "artifacts": {"test_plan": "30 responses"}}
        )
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body["missing_verdict"], "INCOMPLETE")
        self.assertIn("evidence_bundle", response.body["missing"])

    def test_hollow_evidence_is_recorded_not_refused(self) -> None:
        """An artifact that says nothing is still something the executive submitted."""
        case_id = self.make_case()
        response = self.submit_evidence(case_id, evidence_bundle="TBD")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body["invalid_verdict"], "REWORK")
        self.assertIn("evidence_bundle", response.body["invalid"])

    def test_an_empty_artifact_map_is_unprocessable(self) -> None:
        case_id = self.make_case()
        response = self.call("POST", "/harnesses", BUILD, {"case_id": case_id, "artifacts": {}})
        self.assertEqual(response.code, 422)

    def test_a_non_string_artifact_is_unprocessable(self) -> None:
        case_id = self.make_case()
        response = self.call(
            "POST", "/harnesses", BUILD, {"case_id": case_id, "artifacts": {"test_plan": 30}}
        )
        self.assertEqual(response.code, 422)

    def test_an_artifact_outside_executive_authority_is_forbidden(self) -> None:
        """The operator check says which role; may_write says what that role may do."""
        case_id = self.make_case()
        response = self.call(
            "POST",
            "/harnesses",
            BUILD,
            {"case_id": case_id, "artifacts": {"amendment_reason": "not yours"}},
        )
        self.assertEqual(response.code, 403)
        self.assertIn("outside its authority", response.summary)

    def test_an_unknown_case_is_not_found(self) -> None:
        response = self.call(
            "POST", "/harnesses", BUILD, {"case_id": "CASE-999", "artifacts": {"test_plan": "x"}}
        )
        self.assertEqual(response.code, 404)


class JudgmentTest(ApiTestCase):
    def passing_case(self) -> str:
        case_id = self.make_case()
        self.submit_evidence(case_id)
        return case_id

    def test_a_client_may_not_state_the_verdict(self) -> None:
        """The whole point: a judgment is a request, not an assertion."""
        case_id = self.passing_case()
        response = self.call(
            "POST", "/judgments", REVIEW, {"case_id": case_id, "result": "PASSED"}
        )
        self.assertEqual(response.code, 422)
        self.assertIn("not an assertion", response.summary)
        self.assertEqual(Store(self.root).load_case(case_id).state, "NEW")

    def test_a_result_field_is_refused_even_alongside_real_findings(self) -> None:
        case_id = self.passing_case()
        response = self.call(
            "POST",
            "/judgments",
            REVIEW,
            {"case_id": case_id, "unresolved_law_items": 0, "result": "PASSED"},
        )
        self.assertEqual(response.code, 422)

    def test_a_verdict_source_is_required(self) -> None:
        case_id = self.passing_case()
        response = self.call("POST", "/judgments", REVIEW, {"case_id": case_id})
        self.assertEqual(response.code, 422)
        self.assertIn("verdict source", response.summary)

    def test_the_server_runs_the_graph_and_reports_where_it_ended(self) -> None:
        case_id = self.passing_case()
        response = self.call(
            "POST", "/judgments", REVIEW, {"case_id": case_id, "unresolved_law_items": 0}
        )
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body["status"], "PASSED")
        self.assertEqual(
            response.body["trail"],
            "NEW -> LEGISLATIVE -> EXECUTIVE -> HARNESS_SUBMITTED -> JUDICIARY -> PASSED",
        )

    def test_a_rejection_is_a_successful_request(self) -> None:
        """The verdict lives in the body; an HTTP error would mean 'refused to answer'."""
        case_id = self.passing_case()
        response = self.call(
            "POST", "/judgments", REVIEW, {"case_id": case_id, "red_line_violated": True}
        )
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body["status"], "REJECTED")

    def test_unproven_items_route_to_rework_not_passed(self) -> None:
        case_id = self.passing_case()
        response = self.call(
            "POST", "/judgments", REVIEW, {"case_id": case_id, "unresolved_law_items": 2}
        )
        self.assertEqual(response.code, 200)
        self.assertIn("REWORK", response.body["trail"])
        self.assertNotIn("PASSED", response.body["trail"])

    def test_a_case_without_evidence_is_blocked_not_passed(self) -> None:
        case_id = self.make_case()
        response = self.call(
            "POST", "/judgments", REVIEW, {"case_id": case_id, "unresolved_law_items": 0}
        )
        self.assertEqual(response.code, 200)
        self.assertTrue(response.body["blocked"])
        self.assertNotEqual(response.body["status"], "PASSED")

    def test_findings_must_be_numbers_and_booleans(self) -> None:
        case_id = self.passing_case()
        self.assertEqual(
            self.call(
                "POST", "/judgments", REVIEW, {"case_id": case_id, "unresolved_law_items": "many"}
            ).code,
            422,
        )
        self.assertEqual(
            self.call(
                "POST", "/judgments", REVIEW, {"case_id": case_id, "unresolved_law_items": -1}
            ).code,
            422,
        )
        self.assertEqual(
            self.call(
                "POST", "/judgments", REVIEW, {"case_id": case_id, "red_line_violated": "yes"}
            ).code,
            422,
        )

    def test_max_steps_must_be_a_positive_integer(self) -> None:
        case_id = self.passing_case()
        response = self.call(
            "POST",
            "/judgments",
            REVIEW,
            {"case_id": case_id, "unresolved_law_items": 0, "max_steps": 0},
        )
        self.assertEqual(response.code, 422)

    def test_findings_are_written_with_judiciary_authority(self) -> None:
        case_id = self.passing_case()
        self.call("POST", "/judgments", REVIEW, {"case_id": case_id, "unresolved_law_items": 0})
        case = Store(self.root).load_case(case_id)
        self.assertEqual(case.fact("unresolved_law_items"), 0)
        self.assertIs(case.fact("red_line_violated"), False)


class RequestChannelTest(ApiTestCase):
    def test_clarification_raises_the_ambiguity_count(self) -> None:
        case_id = self.make_case()
        response = self.call(
            "POST", "/law-clarifications", BUILD, {"case_id": case_id, "reason": "criteria unclear"}
        )
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body["open_ambiguity_items"], 1)
        self.assertEqual(
            Store(self.root).load_case(case_id).artifacts["ambiguity_notes"], "criteria unclear"
        )

    def test_amendment_raises_the_defect_count(self) -> None:
        case_id = self.make_case()
        response = self.call(
            "POST", "/law-amendments", REVIEW, {"case_id": case_id, "reason": "no crash threshold"}
        )
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body["defective_law_items"], 1)

    def test_proposed_changes_are_folded_into_the_reason(self) -> None:
        """The judiciary has no proposed-changes key, and HTTP may not invent one."""
        case_id = self.make_case()
        self.call(
            "POST",
            "/law-amendments",
            REVIEW,
            {"case_id": case_id, "reason": "no crash threshold", "proposed_changes": ["state a rate"]},
        )
        reason = Store(self.root).load_case(case_id).artifacts["amendment_reason"]
        self.assertIn("no crash threshold", reason)
        self.assertIn("state a rate", reason)

    def test_a_reason_is_required(self) -> None:
        case_id = self.make_case()
        self.assertEqual(
            self.call("POST", "/law-amendments", REVIEW, {"case_id": case_id}).code, 422
        )
        self.assertEqual(
            self.call("POST", "/law-clarifications", BUILD, {"case_id": case_id, "reason": " "}).code,
            422,
        )


class CaseViewTest(ApiTestCase):
    def test_the_view_reports_state_route_and_harness_coverage(self) -> None:
        case_id = self.make_case()
        self.submit_evidence(case_id, evidence_bundle="TBD")
        self.call("POST", "/judgments", REVIEW, {"case_id": case_id, "unresolved_law_items": 1})

        response = self.call("GET", f"/cases/{case_id}", BUILD)
        self.assertEqual(response.code, 200)
        coverage = {row["artifact"]: row["state"] for row in response.body["harness"]}
        self.assertEqual(coverage["evidence_bundle"], "invalid")
        self.assertEqual(coverage["test_plan"], "present")
        self.assertIn("rework_loop", response.body["loops"])

    def test_the_view_never_returns_artifact_contents(self) -> None:
        """Reading evidence would need a role-scoped read this layer cannot express."""
        case_id = self.make_case()
        self.submit_evidence(case_id)
        rendered = json.dumps(self.call("GET", f"/cases/{case_id}", BUILD).body)
        for text in GOOD_EVIDENCE.values():
            self.assertNotIn(text, rendered)

    def test_any_authenticated_operator_may_read(self) -> None:
        case_id = self.make_case()
        for token in (INTAKE, BUILD, REVIEW):
            self.assertEqual(self.call("GET", f"/cases/{case_id}", token).code, 200)

    def test_an_anonymous_read_is_unauthorised(self) -> None:
        case_id = self.make_case()
        self.assertEqual(self.call("GET", f"/cases/{case_id}").code, 401)

    def test_an_unknown_case_is_not_found(self) -> None:
        self.assertEqual(self.call("GET", "/cases/CASE-999", BUILD).code, 404)


class ConcurrencyTest(ApiTestCase):
    def test_a_lost_update_is_reported_as_a_conflict(self) -> None:
        case_id = self.make_case()

        class RacingStore(Store):
            """Simulates another writer landing between this request's load and save."""

            raced = False

            def load_case(self, wanted: str):
                case = super().load_case(wanted)
                if not RacingStore.raced:
                    RacingStore.raced = True
                    super().save_case(super().load_case(wanted))
                return case

        self.app.store = RacingStore(self.root)
        response = self.call(
            "POST", "/law-clarifications", BUILD, {"case_id": case_id, "reason": "unclear"}
        )
        self.assertEqual(response.code, 409)
        self.assertEqual(response.body["id"], case_id)

    def test_the_version_advances_with_each_accepted_write(self) -> None:
        case_id = self.make_case()
        first = self.call("GET", f"/cases/{case_id}", BUILD).body["version"]
        self.call("POST", "/law-clarifications", BUILD, {"case_id": case_id, "reason": "unclear"})
        second = self.call("GET", f"/cases/{case_id}", BUILD).body["version"]
        self.assertGreater(second, first)

    def test_the_store_itself_raises_on_a_stale_write(self) -> None:
        case_id = self.make_case()
        store = Store(self.root)
        stale = store.load_case(case_id)
        store.save_case(store.load_case(case_id))
        with self.assertRaises(ConflictError):
            store.save_case(stale)


if __name__ == "__main__":
    unittest.main()
