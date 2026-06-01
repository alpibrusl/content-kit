from __future__ import annotations

import os

from .base import Writer


class OpenAIWriter(Writer):
    """OpenAI backend. Requires OPENAI_API_KEY."""

    def __init__(self, model: str = "gpt-4o") -> None:
        self.model = model

    def complete(self, system: str, user: str) -> str:
        try:
            import openai
        except ImportError as exc:
            raise RuntimeError(
                "openai is not installed. Run: pip install 'content-kit-core[openai]'"
            ) from exc

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Export it with: export OPENAI_API_KEY=sk-..."
            )

        client = openai.OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=8192,
        )
        return resp.choices[0].message.content or ""
