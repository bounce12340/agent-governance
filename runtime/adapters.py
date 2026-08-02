"""Model interface adapters.

Every adapter speaks HTTP through the standard library, so the runtime inherits
the same zero-dependency rule as the validator. Adding a vendor SDK here would
make `pip install` a precondition for running the governance flow at all.

Request construction is separated from sending so the wire format can be tested
without a network or a credential.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class AdapterError(RuntimeError):
    pass


class MissingCredential(AdapterError):
    pass


class ModelAdapter:
    """Base class. Subclasses own the wire format of one model interface."""

    interface = ""

    def __init__(
        self,
        name: str,
        model: str,
        base_url: str | None = None,
        api_key_env: str | None = None,
        timeout_seconds: int = 60,
        max_output_tokens: int = 4096,
    ) -> None:
        self.name = name
        self.model = model
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"<{type(self).__name__} {self.name} model={self.model}>"

    def credential_present(self) -> bool:
        """Report whether the credential is set, without reading its value."""
        if not self.api_key_env:
            return True
        return bool(os.environ.get(self.api_key_env))

    def resolve_credential(self) -> str:
        if not self.api_key_env:
            raise MissingCredential(f"provider {self.name} declares no api_key_env")
        value = os.environ.get(self.api_key_env)
        if not value:
            # Name the variable, never the value.
            raise MissingCredential(
                f"provider {self.name} needs environment variable {self.api_key_env}"
            )
        return value

    def build_request(self, system: str, prompt: str) -> tuple[str, dict[str, str], bytes]:
        raise NotImplementedError

    def parse_response(self, payload: dict[str, Any]) -> str:
        raise NotImplementedError

    def complete(self, system: str, prompt: str) -> str:
        url, headers, body = self.build_request(system, prompt)
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # The response body can echo request headers, so it is not surfaced.
            raise AdapterError(
                f"provider {self.name} returned HTTP {exc.code}"
            ) from None
        except urllib.error.URLError as exc:
            raise AdapterError(f"provider {self.name} is unreachable: {exc.reason}") from None
        return self.parse_response(payload)


class OpenAIChatCompletionsAdapter(ModelAdapter):
    """Any endpoint speaking the OpenAI chat-completions shape.

    That covers OpenAI itself and the many servers that copy it, including
    self-hosted ones. `max_output_tokens` is deliberately not sent: the field
    name for it differs across implementations, and omitting it is the one
    choice every implementation accepts.
    """

    interface = "openai_chat_completions"

    def build_request(self, system: str, prompt: str) -> tuple[str, dict[str, str], bytes]:
        if not self.base_url:
            raise AdapterError(f"provider {self.name} has no base_url")
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.resolve_credential()}",
            "Content-Type": "application/json",
        }
        return f"{self.base_url}/chat/completions", headers, json.dumps(body).encode("utf-8")

    def parse_response(self, payload: dict[str, Any]) -> str:
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise AdapterError(f"provider {self.name} returned an unrecognised response") from None


class AnthropicMessagesAdapter(ModelAdapter):
    """The Anthropic messages interface, which requires an explicit token cap."""

    interface = "anthropic_messages"
    api_version = "2023-06-01"

    def build_request(self, system: str, prompt: str) -> tuple[str, dict[str, str], bytes]:
        if not self.base_url:
            raise AdapterError(f"provider {self.name} has no base_url")
        body = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self.resolve_credential(),
            "anthropic-version": self.api_version,
            "content-type": "application/json",
        }
        return f"{self.base_url}/messages", headers, json.dumps(body).encode("utf-8")

    def parse_response(self, payload: dict[str, Any]) -> str:
        try:
            return payload["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise AdapterError(f"provider {self.name} returned an unrecognised response") from None


class StubAdapter(ModelAdapter):
    """Deterministic, offline, credential-free.

    This is what lets CI exercise the full governance flow without a key and
    without network access.
    """

    interface = "stub"

    def build_request(self, system: str, prompt: str) -> tuple[str, dict[str, str], bytes]:
        raise AdapterError("the stub interface performs no network I/O")

    def complete(self, system: str, prompt: str) -> str:
        return f"[{self.name}] system={len(system)} prompt={len(prompt)}"


class ScriptedAdapter(ModelAdapter):
    """Replays queued replies instead of calling a model.

    Deliberately absent from INTERFACES: this is a test double, not something a
    config should be able to put in a governance seat.
    """

    interface = "scripted"

    def __init__(self, name: str, replies: list[str], model: str = "scripted") -> None:
        super().__init__(name=name, model=model)
        self.replies = list(replies)
        self.asked: list[tuple[str, str]] = []

    def build_request(self, system: str, prompt: str) -> tuple[str, dict[str, str], bytes]:
        raise AdapterError("the scripted adapter performs no network I/O")

    def complete(self, system: str, prompt: str) -> str:
        self.asked.append((system, prompt))
        if not self.replies:
            raise AdapterError(f"scripted adapter {self.name} ran out of replies")
        return self.replies.pop(0)


INTERFACES: dict[str, type[ModelAdapter]] = {
    OpenAIChatCompletionsAdapter.interface: OpenAIChatCompletionsAdapter,
    AnthropicMessagesAdapter.interface: AnthropicMessagesAdapter,
    StubAdapter.interface: StubAdapter,
}


def build_adapter(name: str, provider: dict[str, Any]) -> ModelAdapter:
    interface = provider.get("interface")
    adapter_class = INTERFACES.get(str(interface))
    if adapter_class is None:
        raise AdapterError(f"provider {name} declares unknown interface: {interface}")
    return adapter_class(
        name=name,
        model=str(provider.get("model")),
        base_url=provider.get("base_url"),
        api_key_env=provider.get("api_key_env"),
        timeout_seconds=int(provider.get("timeout_seconds", 60)),
        max_output_tokens=int(provider.get("max_output_tokens", 4096)),
    )
