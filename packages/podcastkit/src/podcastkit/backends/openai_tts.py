from __future__ import annotations

import os
from pathlib import Path

from ..config import VoiceConfig
from .base import Backend

MIN_VALID_BYTES = 5 * 1024
DEFAULT_MODEL = "tts-1-hd"


class OpenAIBackend(Backend):
    def synthesize(self, text: str, voice: VoiceConfig, dest: Path) -> None:
        """Generate TTS audio via the OpenAI Audio Speech API and write MP3 to dest.

        voice.voice_id is the OpenAI voice name (e.g. 'alloy', 'echo', 'nova').
        voice.model_id overrides the model (default: 'tts-1-hd').
        API key is read from the OPENAI_API_KEY environment variable.
        """
        if dest.exists() and dest.stat().st_size >= MIN_VALID_BYTES:
            return

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set in environment. "
                "Export it with: export OPENAI_API_KEY=sk-..."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai package is not installed. Install the openai extra: "
                "pip install 'podcastkit[openai]'"
            ) from exc

        client = OpenAI(api_key=api_key)
        model = voice.model_id if voice.model_id else DEFAULT_MODEL

        response = client.audio.speech.create(
            model=model,
            voice=voice.voice_id,  # type: ignore[arg-type]
            input=text,
            response_format="mp3",
        )

        dest.parent.mkdir(parents=True, exist_ok=True)
        response.stream_to_file(dest)

        size = dest.stat().st_size
        if size < MIN_VALID_BYTES:
            dest.unlink(missing_ok=True)
            raise RuntimeError(
                f"OpenAI TTS response too small ({size} bytes) for {dest.name} "
                f"— likely a silent or empty response."
            )
