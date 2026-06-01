from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..config import VoiceConfig


class Backend(ABC):
    @abstractmethod
    def synthesize(self, text: str, voice: VoiceConfig, dest: Path) -> None:
        """Generate TTS audio for text and write MP3 to dest."""
