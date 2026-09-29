"""Offline tests for the runtime. No network, no credentials, no dependencies."""

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

from runtime.adapters import (  # noqa: E402
    AdapterError,
    AnthropicMessagesAdapter,
    MissingCredential,
    OpenAIChatCompletionsAdapter,
    StubAdapter,
    build_adapter,
)
from runtime.roles import IsolationError, RoleSession  # noqa: E402
from runtime.session import GovernanceSession  # noqa: E402
from validate_governance import validate_config  # noqa: E402

CONFIG = json.loads((REPO_ROOT / "config" / "governance.json").read_text(encoding="utf-8"))


class OpenAIInterfaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = OpenAIChatCompletionsAdapter(
            name="test_openai",
            model="some-model",
            base_url="https://example.invalid/v1/",
            api_key_env="TEST_OPENAI_KEY",
        )
        os.environ["TEST_OPENAI_KEY"] = "not-a-real-key"
        self.addCleanup(os.environ.pop, "TEST_OPENAI_KEY", None)

    def test_request_shape(self) -> None:
        url, headers, body = self.adapter.build_request("SYS", "PROMPT")
        self.assertEqual(url, "https://example.invalid/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer not-a-real-key")
        payload = json.loads(body)
        self.assertEqual(payload["model"], "some-model")
        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": "SYS"},
                {"role": "user", "content": "PROMPT"},
            ],
        )

    def test_response_parsing(self) -> None:
        payload = {"choices": [{"message": {"content": "hello"}}]}
        self.assertEqual(self.adapter.parse_response(payload), "hello")

    def test_unrecognised_response_is_an_error(self) -> None:
        with self.assertRaises(AdapterError):
            self.adapter.parse_response({"unexpected": True})


class AnthropicInterfaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = AnthropicMessagesAdapter(
            name="test_anthropic",
            model="some-model",
            base_url="https://example.invalid/v1",
            api_key_env="TEST_ANTHROPIC_KEY",
            max_output_tokens=256,
        )
        os.environ["TEST_ANTHROPIC_KEY"] = "not-a-real-key"
        self.addCleanup(os.environ.pop, "TEST_ANTHROPIC_KEY", None)

    def test_request_shape(self) -> None:
        url, headers, body = self.adapter.build_request("SYS", "PROMPT")
        self.assertEqual(url, "https://example.invalid/v1/messages")
        self.assertEqual(headers["x-api-key"], "not-a-real-key")
        self.assertIn("anthropic-version", headers)
        payload = json.loads(body)
        self.assertEqual(payload["system"], "SYS")
        self.assertEqual(payload["max_tokens"], 256)
        self.assertEqual(payload["messages"], [{"role": "user", "content": "PROMPT"}])

    def test_response_parsing(self) -> None:
        self.assertEqual(
            self.adapter.parse_response({"content": [{"text": "hello"}]}), "hello"
        )


class CredentialTest(unittest.TestCase):
    def test_missing_credential_names_the_variable_not_the_value(self) -> None:
        adapter = OpenAIChatCompletionsAdapter(
            name="test_openai",
            model="m",
            base_url="https://example.invalid/v1",
            api_key_env="DEFINITELY_UNSET_KEY_FOR_TESTS",
        )
        self.assertFalse(adapter.credential_present())
        with self.assertRaises(MissingCredential) as caught:
            adapter.build_request("SYS", "PROMPT")
        self.assertIn("DEFINITELY_UNSET_KEY_FOR_TESTS", str(caught.exception))

    def test_stub_needs_no_credential(self) -> None:
        stub = StubAdapter(name="offline_stub", model="stub")
        self.assertTrue(stub.credential_present())
        self.assertTrue(stub.complete("SYS", "PROMPT").startswith("[offline_stub]"))

    def test_stub_refuses_network_io(self) -> None:
        with self.assertRaises(AdapterError):
            StubAdapter(name="offline_stub", model="stub").build_request("SYS", "PROMPT")


class ModelOverrideTest(unittest.TestCase):
    """A model id in the config is a default, not a fact. Vendors retire them."""

    def build(self, **override) -> OpenAIChatCompletionsAdapter:
        provider = {
            "interface": "openai_chat_completions",
            "model": "configured-model",
            "base_url": "https://example.invalid/v1",
            "api_key_env": "TEST_OPENAI_KEY",
            "model_env": "TEST_MODEL_OVERRIDE",
        }
        provider.update(override)
        return build_adapter("test_openai", provider)

    def test_the_config_value_is_used_when_nothing_overrides_it(self) -> None:
        os.environ.pop("TEST_MODEL_OVERRIDE", None)
        adapter = self.build()
        self.assertEqual(adapter.model, "configured-model")
        self.assertEqual(adapter.model_source, "config")

    def test_the_environment_wins_when_set(self) -> None:
        os.environ["TEST_MODEL_OVERRIDE"] = "newer-model"
        self.addCleanup(os.environ.pop, "TEST_MODEL_OVERRIDE", None)
        adapter = self.build()
        self.assertEqual(adapter.model, "newer-model")
        self.assertEqual(adapter.model_source, "TEST_MODEL_OVERRIDE")

    def test_an_empty_override_falls_back_rather_than_sending_nothing(self) -> None:
        """An unset variable and an empty one mean the same thing to a shell."""
        os.environ["TEST_MODEL_OVERRIDE"] = ""
        self.addCleanup(os.environ.pop, "TEST_MODEL_OVERRIDE", None)
        adapter = self.build()
        self.assertEqual(adapter.model, "configured-model")

    def test_a_provider_may_decline_an_override(self) -> None:
        os.environ["TEST_MODEL_OVERRIDE"] = "newer-model"
        self.addCleanup(os.environ.pop, "TEST_MODEL_OVERRIDE", None)
        adapter = self.build(model_env=None)
        self.assertEqual(adapter.model, "configured-model")

    def test_the_override_reaches_the_wire(self) -> None:
        os.environ["TEST_MODEL_OVERRIDE"] = "newer-model"
        os.environ["TEST_OPENAI_KEY"] = "not-a-real-key"
        self.addCleanup(os.environ.pop, "TEST_MODEL_OVERRIDE", None)
        self.addCleanup(os.environ.pop, "TEST_OPENAI_KEY", None)
        _, _, body = self.build().build_request("SYS", "PROMPT")
        self.assertEqual(json.loads(body)["model"], "newer-model")

    def test_the_report_says_where_the_model_came_from(self) -> None:
        os.environ["OPENAI_MODEL"] = "newer-model"
        self.addCleanup(os.environ.pop, "OPENAI_MODEL", None)
        rows = {row["role"]: row for row in GovernanceSession(copy.deepcopy(CONFIG)).report()}
        self.assertEqual(rows["executive"]["model_source"], "OPENAI_MODEL")
        self.assertEqual(rows["legislative"]["model_source"], "config")


class RoleIsolationTest(unittest.TestCase):
    def make_role(self, role: str) -> RoleSession:
        cfg = CONFIG["role_isolation"][role]
        return RoleSession(
            role=role,
            adapter=StubAdapter(name="offline_stub", model="stub"),
            prompt_scope=cfg["prompt_scope"],
            may_read=cfg["may_read"],
            may_not_read=cfg["may_not_read"],
        )

    def test_forbidden_material_is_rejected(self) -> None:
        judiciary = self.make_role("judiciary")
        with self.assertRaises(IsolationError) as caught:
            judiciary.build_context({"law": "L", "executive_private_notes": "secret"})
        self.assertIn("executive_private_notes", str(caught.exception))

    def test_context_is_an_allowlist_not_a_passthrough(self) -> None:
        judiciary = self.make_role("judiciary")
        context = judiciary.build_context(
            {"law": "L", "harness_artifacts": "H", "unlisted_material": "U"}
        )
        self.assertIn("## law", context)
        self.assertIn("## harness_artifacts", context)
        self.assertNotIn("unlisted_material", context)

    def test_system_prompt_states_both_boundaries(self) -> None:
        prompt = self.make_role("legislative").system_prompt()
        self.assertIn("law_writing_only", prompt)
        self.assertIn("executive_private_notes", prompt)


class SessionWiringTest(unittest.TestCase):
    def test_every_role_binds_to_its_declared_provider(self) -> None:
        session = GovernanceSession(copy.deepcopy(CONFIG))
        self.assertEqual(
            {row["role"]: row["provider"] for row in session.report()},
            {
                "legislative": "anthropic_primary",
                "executive": "openai_primary",
                "judiciary": "openai_compatible_local",
            },
        )

    def test_roles_do_not_share_a_model(self) -> None:
        session = GovernanceSession(copy.deepcopy(CONFIG))
        models = [(row["interface"], row["base_url"], row["model"]) for row in session.report()]
        self.assertEqual(len(set(models)), len(models))

    def test_report_never_exposes_a_credential(self) -> None:
        os.environ["OPENAI_API_KEY"] = "super-secret-value"
        self.addCleanup(os.environ.pop, "OPENAI_API_KEY", None)
        session = GovernanceSession(copy.deepcopy(CONFIG))
        self.assertNotIn("super-secret-value", json.dumps(session.report()))

    def test_loop_bounds_come_from_the_config(self) -> None:
        session = GovernanceSession(copy.deepcopy(CONFIG))
        self.assertEqual(session.loop_bound("rework_loop"), CONFIG["constitution"]["max_rework_count"])

    def test_unknown_interface_is_refused(self) -> None:
        with self.assertRaises(AdapterError):
            build_adapter("bogus", {"interface": "carrier_pigeon", "model": "m"})


class ConfigContractTest(unittest.TestCase):
    """The runtime trusts the config, so the config must stay enforced."""

    def mutated(self, mutate) -> list[str]:
        doc = copy.deepcopy(CONFIG)
        mutate(doc)
        return validate_config(doc)

    def test_shipped_config_passes(self) -> None:
        self.assertEqual(validate_config(copy.deepcopy(CONFIG)), [])

    def test_roles_sharing_one_model_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["role_isolation"]["judiciary"].__setitem__("provider", "openai_primary")
        )
        self.assertTrue(any("not isolated" in e for e in errors), errors)

    def test_undeclared_provider_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["role_isolation"]["executive"].__setitem__("provider", "nope")
        )
        self.assertTrue(any("not a declared provider" in e for e in errors), errors)

    def test_literal_key_in_config_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["providers"]["openai_primary"].__setitem__("api_key_env", "sk-abc123")
        )
        self.assertTrue(any("api_key_env" in e for e in errors), errors)

    def test_unknown_interface_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["providers"]["openai_primary"].__setitem__("interface", "carrier_pigeon")
        )
        self.assertTrue(any("interface must be one of" in e for e in errors), errors)

    def test_a_literal_model_id_in_model_env_is_rejected(self) -> None:
        errors = self.mutated(
            lambda d: d["providers"]["openai_primary"].__setitem__("model_env", "gpt-4o")
        )
        self.assertTrue(any("model_env" in e for e in errors), errors)

    def test_a_provider_may_declare_no_override(self) -> None:
        errors = self.mutated(
            lambda d: d["providers"]["openai_primary"].__setitem__("model_env", None)
        )
        self.assertEqual(errors, [])

    def test_a_provider_missing_model_env_entirely_is_rejected(self) -> None:
        errors = self.mutated(lambda d: d["providers"]["openai_primary"].pop("model_env"))
        self.assertTrue(any("model_env" in e for e in errors), errors)

    def test_known_interfaces_match_the_runtime_registry(self) -> None:
        from runtime.adapters import INTERFACES
        from validate_governance import KNOWN_INTERFACES

        self.assertEqual(set(INTERFACES), KNOWN_INTERFACES)


if __name__ == "__main__":
    unittest.main()
