"""Offline tests for operator authentication and authorisation.

The CLI could treat filesystem access as its authorisation: whoever can run the
binary can already read the store. HTTP has no such boundary, so these are the
tests that keep an unauthenticated request from acting as any role it likes.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from runtime.operators import AuthError, Operator, OperatorRegistry  # noqa: E402
from validate_governance import validate_config  # noqa: E402

CONFIG = json.loads((REPO_ROOT / "config" / "governance.json").read_text(encoding="utf-8"))

TOKENS = {
    "AI_GOV_TOKEN_INTAKE": "intake-token",
    "AI_GOV_TOKEN_BUILD": "build-token",
    "AI_GOV_TOKEN_REVIEWER": "reviewer-token",
}


class RegistryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        for name, value in TOKENS.items():
            os.environ[name] = value
            self.addCleanup(os.environ.pop, name, None)
        self.registry = OperatorRegistry(copy.deepcopy(CONFIG))


class AuthenticationTest(RegistryTestCase):
    def test_a_configured_token_resolves_to_its_operator(self) -> None:
        operator = self.registry.authenticate("reviewer-token")
        self.assertIsNotNone(operator)
        self.assertEqual(operator.name, "reviewer")

    def test_an_unknown_token_resolves_to_nobody(self) -> None:
        self.assertIsNone(self.registry.authenticate("not-a-token"))

    def test_an_empty_token_resolves_to_nobody(self) -> None:
        self.assertIsNone(self.registry.authenticate(""))
        self.assertIsNone(self.registry.authenticate(None))

    def test_an_unset_variable_never_authenticates(self) -> None:
        """An absent credential must not authenticate as an absent token."""
        os.environ.pop("AI_GOV_TOKEN_REVIEWER", None)
        registry = OperatorRegistry(copy.deepcopy(CONFIG))
        self.assertIsNone(registry.authenticate("reviewer-token"))
        self.assertIsNone(registry.authenticate(""))
        self.assertIsNone(registry.authenticate(None))

    def test_a_prefix_of_a_real_token_is_not_a_match(self) -> None:
        self.assertIsNone(self.registry.authenticate("reviewer-tok"))
        self.assertIsNone(self.registry.authenticate("reviewer-token-and-more"))

    def test_tokens_do_not_leak_between_operators(self) -> None:
        self.assertEqual(self.registry.authenticate("build-token").name, "build_bot")
        self.assertEqual(self.registry.authenticate("intake-token").name, "intake_bot")


class AuthorisationTest(RegistryTestCase):
    def test_an_operator_may_act_as_its_declared_role(self) -> None:
        operator = self.registry.authenticate("reviewer-token")
        self.assertIs(self.registry.authorise(operator, "judiciary"), operator)

    def test_an_operator_may_not_act_as_another_role(self) -> None:
        operator = self.registry.authenticate("reviewer-token")
        with self.assertRaises(AuthError) as caught:
            self.registry.authorise(operator, "executive")
        self.assertIn("reviewer", str(caught.exception))
        self.assertIn("executive", str(caught.exception))

    def test_nobody_may_act_as_anything(self) -> None:
        with self.assertRaises(AuthError):
            self.registry.authorise(None, "judiciary")

    def test_every_role_has_exactly_one_operator_in_the_shipped_config(self) -> None:
        """Not a rule the validator enforces, but the shipped wiring should be plain."""
        claimed = [role for op in self.registry.operators.values() for role in op.roles]
        self.assertEqual(sorted(claimed), sorted(CONFIG["role_isolation"]))


class ReportTest(RegistryTestCase):
    def test_the_report_says_present_never_the_value(self) -> None:
        rendered = json.dumps(self.registry.report())
        self.assertIn("set", rendered)
        for value in TOKENS.values():
            self.assertNotIn(value, rendered)

    def test_a_missing_credential_is_reported_as_missing(self) -> None:
        os.environ.pop("AI_GOV_TOKEN_BUILD", None)
        registry = OperatorRegistry(copy.deepcopy(CONFIG))
        rows = {row["operator"]: row["credential"] for row in registry.report()}
        self.assertEqual(rows["build_bot"], "missing")
        self.assertEqual(rows["reviewer"], "set")

    def test_an_operator_with_no_variable_name_is_simply_unusable(self) -> None:
        operator = Operator(name="ghost", token_env="", roles=["judiciary"])
        self.assertFalse(operator.credential_present())
        self.assertIsNone(operator.token())


class ConfigContractTest(unittest.TestCase):
    def mutated(self, mutate) -> list[str]:
        doc = copy.deepcopy(CONFIG)
        mutate(doc)
        return validate_config(doc)

    def test_shipped_config_passes(self) -> None:
        self.assertEqual(validate_config(copy.deepcopy(CONFIG)), [])

    def test_a_literal_token_in_the_config_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["operators"]["reviewer"].__setitem__("token_env", "sk-live-abc123")
        )
        self.assertTrue(any("token_env" in e for e in errors), errors)

    def test_two_operators_sharing_one_variable_are_rejected(self) -> None:
        """Indistinguishable operators defeat the point of naming them separately."""
        errors = self.mutated(
            lambda d: d["operators"]["build_bot"].__setitem__(
                "token_env", d["operators"]["reviewer"]["token_env"]
            )
        )
        self.assertTrue(any("already used by" in e for e in errors), errors)

    def test_an_undeclared_role_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["operators"]["reviewer"].__setitem__("may_act_as", ["monarch"])
        )
        self.assertTrue(any("undeclared roles" in e for e in errors), errors)

    def test_an_operator_that_may_act_as_nothing_is_rejected(self) -> None:
        errors = self.mutated(lambda d: d["operators"]["reviewer"].__setitem__("may_act_as", []))
        self.assertTrue(any("may_act_as must not be empty" in e for e in errors), errors)

    def test_an_empty_operator_table_is_rejected(self) -> None:
        errors = self.mutated(lambda d: d.__setitem__("operators", {}))
        self.assertTrue(any("at least one operator" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
