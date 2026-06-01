from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from ..config import VoiceConfig
from .base import Backend

API_BASE = "https://api.elevenlabs.io/v1/text-to-speech"
MIN_VALID_BYTES = 5 * 1024
MAX_RETRIES = 3
POLITE_SLEEP = 1.0


class ElevenLabsBackend(Backend):
    def synthesize(self, text: str, voice: VoiceConfig, dest: Path) -> None:
        """POST text to ElevenLabs TTS API and write MP3 to dest.

        Skips if dest already exists and is >= 5 KB.
        Retries with exponential backoff; handles 429 rate limiting.
        """
        if dest.exists() and dest.stat().st_size >= MIN_VALID_BYTES:
            return

        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY is not set in environment. "
                "Export it with: export ELEVENLABS_API_KEY=sk_..."
            )

        url = f"{API_BASE}/{voice.voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        body: dict = {
            "text": text,
            "model_id": voice.model_id or "eleven_multilingual_v2",
        }
        if voice.settings:
            body["voice_settings"] = voice.settings

        backoff = 2
        for attempt in range(1, MAX_RETRIES + 1):
            resp = requests.post(url, headers=headers, json=body, timeout=60)
            if resp.status_code == 200:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(resp.content)
                size = dest.stat().st_size
                if size < MIN_VALID_BYTES:
                    dest.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"ElevenLabs response too small ({size} bytes) for {dest.name} "
                        f"— likely a silent failure. Delete and retry."
                    )
                return
            if resp.status_code == 401:
                raise RuntimeError("401 Unauthorized from ElevenLabs — check ELEVENLABS_API_KEY.")
            if resp.status_code == 404:
                raise RuntimeError(
                    f"404 from ElevenLabs for voice_id '{voice.voice_id}' — "
                    f"the voice may no longer be in the public catalog. "
                    f"Provide a replacement voice_id in episode.yaml."
                )
            if resp.status_code == 429:
                wait = 30
                print(f"  ! 429 rate-limited, sleeping {wait}s")
                time.sleep(wait)
                continue
            print(f"  ! attempt {attempt} got {resp.status_code}: {resp.text[:200]}")
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"ElevenLabs: failed after {MAX_RETRIES} attempts "
                    f"(last status {resp.status_code}) for {dest.name}"
                )
            time.sleep(backoff)
            backoff *= 2
