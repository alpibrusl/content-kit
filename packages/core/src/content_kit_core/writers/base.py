from __future__ import annotations

from abc import ABC, abstractmethod


class Writer(ABC):
    """LLM backend for text generation."""

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Send a system + user message and return the full text response."""
