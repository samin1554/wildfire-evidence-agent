"""The agent's language model: it plans and explains; it never calculates (spec §14, ADR-007).

Calls go through the connector kit (allowlisted host, key from env, redaction, retries), like every provider.
`ScriptedLLM` stands in for tests and offline runs, so the test suite never needs a key or network.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from pydantic import BaseModel

from inland_worker.kit.config import ProviderConfig, load_providers
from inland_worker.kit.connector import ProviderRequest
from inland_worker.kit.errors import ProviderError
from inland_worker.kit.http import KitHttpClient

# Free OpenRouter models with tool support, tried in order (OpenRouter falls back automatically).
# Free models rotate: override with AGENT_MODELS=model1,model2 in .env. Verified available Sep 24, 2026.
DEFAULT_MODELS = ["qwen/qwen3.8-27b:free", "google/gemma-4-31b-it:free", "nex-agi/nex-n2.5-pro:free"]


class LLMReply(BaseModel):
    text: str
    model: str


class LLM(Protocol):
    async def complete(self, messages: Sequence[dict[str, str]], *, max_tokens: int = 1200) -> LLMReply: ...


class OpenRouterLLM:
    def __init__(
        self,
        models: Sequence[str] | None = None,
        *,
        config: ProviderConfig | None = None,
        client: KitHttpClient | None = None,
    ):
        env_models = [m.strip() for m in os.environ.get("AGENT_MODELS", "").split(",") if m.strip()]
        self.models = list(models or env_models or DEFAULT_MODELS)
        self.config = config or load_providers().get("openrouter")
        self.client = client or KitHttpClient(self.config)

    async def complete(self, messages: Sequence[dict[str, str]], *, max_tokens: int = 1200) -> LLMReply:
        body = {"models": self.models, "messages": list(messages), "temperature": 0, "max_tokens": max_tokens}
        resp = await self.client.get(
            ProviderRequest(method="POST", path="/chat/completions", json_body=body, label="chat")
        )
        data = resp.json()
        if "error" in data:  # OpenRouter can report errors with HTTP 200
            raise ProviderError(
                self.config.provider_id, f"LLM error: {data['error'].get('message', data['error'])}"
            )
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderError(self.config.provider_id, "LLM response had no message content") from None
        return LLMReply(text=text, model=data.get("model", self.models[0]))


class ScriptedLLM:
    """Test double: returns queued replies (or computes them from the messages) and records every call."""

    def __init__(
        self,
        replies: Sequence[str | Callable[[Sequence[dict[str, str]]], str]] = (),
        *,
        fail: bool = False,
        model: str = "scripted",
    ):
        self.replies = list(replies)
        self.fail = fail
        self.model = model
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages: Sequence[dict[str, str]], *, max_tokens: int = 1200) -> LLMReply:
        self.calls.append(list(messages))
        if self.fail or not self.replies:
            raise ProviderError("scripted", "LLM unavailable")
        reply = self.replies.pop(0)
        return LLMReply(text=reply(messages) if callable(reply) else reply, model=self.model)


def extract_json(text: str) -> Any:
    """Models often wrap JSON in prose or ``` fences: take the first balanced {...} object."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        return json.loads(fenced.group(1))
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in model output")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        depth += ch == "{"
        depth -= ch == "}"
        if depth == 0:
            return json.loads(text[start : i + 1])
    raise ValueError("unbalanced JSON object in model output")
