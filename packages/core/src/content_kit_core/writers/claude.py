from __future__ import annotations

import os

from .base import Writer


class ClaudeWriter(Writer):
    """Anthropic Claude backend. Requires ANTHROPIC_API_KEY."""

    def __init__(self, model: str = "claude-opus-4-7") -> None:
        self.model = model

    def complete(self, system: str, user: str) -> str:
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic is not installed. Run: pip install 'content-kit-core[claude]'"
            ) from exc

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Export it with: export ANTHROPIC_API_KEY=sk-ant-..."
            )

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text
