from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import VoiceConfig
from ._util import write_mp3_from_pcm
from .base import Backend

MIN_VALID_BYTES = 5 * 1024
KOKORO_SAMPLE_RATE = 24000

# Cache one KPipeline per language prefix ('a' for American, 'b' for British).
_pipelines: dict[str, Any] = {}


def _get_pipeline(voice_name: str) -> Any:
    """Return a cached KPipeline for the language prefix of voice_name.

    Kokoro's American (a) and British (b) phonemizers differ — pick the one
    that matches the voice prefix (e.g. 'af_bella' -> 'a', 'bm_george' -> 'b').
    """
    try:
        from kokoro import KPipeline
    except ImportError as exc:
        raise RuntimeError(
            "Kokoro is not installed. Install the kokoro extra: pip install 'podcastkit[kokoro]'"
        ) from exc

    lang = voice_name[0]  # 'a' for af_/am_, 'b' for bf_/bm_
    if lang not in _pipelines:
        _pipelines[lang] = KPipeline(lang_code=lang)
    return _pipelines[lang]


class KokoroBackend(Backend):
    def synthesize(self, text: str, voice: VoiceConfig, dest: Path) -> None:
        """Generate TTS audio via Kokoro (local, open-source) and write MP3 to dest.

        voice.voice_id must be a Kokoro voice name such as 'bm_george' or 'af_bella'.
        KPipeline instances are cached by language prefix to avoid repeated initialisation.
        """
        if dest.exists() and dest.stat().st_size >= MIN_VALID_BYTES:
            return

        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError(
                "numpy is not installed. Install the kokoro extra: pip install 'podcastkit[kokoro]'"
            ) from exc

        voice_name = voice.voice_id
        pipeline = _get_pipeline(voice_name)

        chunks = []
        for _, _, audio in pipeline(text, voice=voice_name):
            # Kokoro may return torch tensors — convert to numpy.
            chunks.append(audio.cpu().numpy() if hasattr(audio, "cpu") else np.asarray(audio))

        if not chunks:
            raise RuntimeError(f"Kokoro produced no audio for voice '{voice_name}': {text[:60]!r}")

        dest.parent.mkdir(parents=True, exist_ok=True)
        write_mp3_from_pcm(np.concatenate(chunks), KOKORO_SAMPLE_RATE, dest)

        size = dest.stat().st_size
        if size < MIN_VALID_BYTES:
            dest.unlink(missing_ok=True)
            raise RuntimeError(
                f"Kokoro output too small ({size} bytes) for {dest.name} "
                f"— likely a silent/empty generation."
            )
