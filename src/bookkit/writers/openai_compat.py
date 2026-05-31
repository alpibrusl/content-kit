from __future__ import annotations

import os

import requests

from .base import Writer


class OpenAICompatWriter(Writer):
    """Generic OpenAI-compatible chat backend — the key to being LLM-agnostic.

    Talks to any endpoint that implements ``POST {base_url}/chat/completions``:
    local servers (llama.cpp, vLLM, LM Studio, Ollama's OpenAI-compat API) and
    hosted gateways (OpenRouter, Together, Groq, Fireworks, Azure, ...). It uses
    plain HTTP via requests (a core dependency), so no provider SDK or extra is
    required.

    Configuration (all overridable via constructor args):
      BOOKKIT_LLM_BASE_URL   e.g. http://localhost:8080/v1  or  https://openrouter.ai/api/v1
      BOOKKIT_LLM_API_KEY    bearer token (optional for local servers)
      BOOKKIT_MODEL          model id, e.g. llama-3.1-8b-instruct
    """

    def __init__(
        self,
        model: str | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("BOOKKIT_LLM_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.environ.get("BOOKKIT_LLM_API_KEY") or ""
        self.model = model or os.environ.get("BOOKKIT_MODEL") or "gpt-4o-mini"

    def complete(self, system: str, user: str) -> str:
        if not self.base_url:
            raise RuntimeError(
                "BOOKKIT_LLM_BASE_URL is not set. Point it at any OpenAI-compatible "
                "endpoint, e.g. export BOOKKIT_LLM_BASE_URL=http://localhost:8080/v1"
            )
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=300,
            )
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Cannot connect to OpenAI-compatible endpoint at {self.base_url}."
            ) from exc
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""
