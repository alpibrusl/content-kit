from __future__ import annotations

import requests

from .base import Writer

OLLAMA_URL = "http://localhost:11434/api/chat"


class OllamaWriter(Writer):
    """Local Ollama backend — no API key required.

    Requires Ollama running at localhost:11434.
    Install: https://ollama.com  then: ollama pull llama3.2
    """

    def __init__(self, model: str = "llama3.2") -> None:
        self.model = model

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=300)
        except requests.ConnectionError as exc:
            raise RuntimeError(
                "Cannot connect to Ollama at localhost:11434. "
                "Is Ollama running? Start it with: ollama serve"
            ) from exc
        if resp.status_code == 404:
            raise RuntimeError(
                f"Model '{self.model}' not found in Ollama. Pull it first: ollama pull {self.model}"
            )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
