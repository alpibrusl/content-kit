from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import VoiceConfig
from ._util import write_mp3_from_pcm
from .base import Backend

MIN_VALID_BYTES = 5 * 1024

# Cache loaded models: key = "<model_type>:<device>"
_models: dict[str, Any] = {}


def _get_model(model_type: str, device: str) -> Any:
    key = f"{model_type}:{device}"
    if key in _models:
        return _models[key]

    try:
        if model_type == "turbo":
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            _models[key] = ChatterboxTurboTTS.from_pretrained(device=device)
        elif model_type == "multilingual":
            from chatterbox.tts_multilingual import ChatterboxMultilingualTTS

            _models[key] = ChatterboxMultilingualTTS.from_pretrained(device=device)
        else:
            from chatterbox.tts import ChatterboxTTS

            _models[key] = ChatterboxTTS.from_pretrained(device=device)
    except ImportError as exc:
        raise RuntimeError(
            "chatterbox-tts is not installed. Install the chatterbox extra: "
            "pip install 'podcastkit[chatterbox]'"
        ) from exc

    return _models[key]


class ChatterboxBackend(Backend):
    """Chatterbox TTS backend (local, open-source, supports voice cloning).

    VoiceConfig fields:
      voice_id  — path to a reference audio file for voice cloning, or "" for
                  the model's default voice.
      model_id  — which Chatterbox model to load: "standard" (default) |
                  "turbo" | "multilingual".
      settings  — optional generation knobs:
                    device:       "cuda" | "cpu"  (default: cuda if available)
                    language_id:  ISO code (e.g. "es", "fr") — multilingual model only
                    exaggeration: 0.25-2.0  emotion intensity  (default 0.5)
                    cfg_weight:   0.0-1.0   pace control       (default 0.5)
                    temperature:  0.05-5.0  output consistency (default 0.8)
    """

    def synthesize(self, text: str, voice: VoiceConfig, dest: Path) -> None:
        if dest.exists() and dest.stat().st_size >= MIN_VALID_BYTES:
            return

        try:
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "torch is not installed. Install the chatterbox extra: "
                "pip install 'podcastkit[chatterbox]'"
            ) from exc

        settings = voice.settings
        model_type = voice.model_id or "standard"
        device = settings.get("device", "cuda" if torch.cuda.is_available() else "cpu")

        model = _get_model(model_type, device)

        kwargs: dict[str, Any] = {}
        if voice.voice_id:
            kwargs["audio_prompt_path"] = voice.voice_id
        # language_id selects the target language for the multilingual model.
        if model_type == "multilingual" and "language_id" in settings:
            kwargs["language_id"] = settings["language_id"]
        for key in ("exaggeration", "cfg_weight", "temperature"):
            if key in settings:
                kwargs[key] = settings[key]

        wav = model.generate(text, **kwargs)

        # wav is a tensor of shape [1, samples]; model.sr is the sample rate.
        audio_np = wav.squeeze(0).cpu().numpy()
        dest.parent.mkdir(parents=True, exist_ok=True)
        write_mp3_from_pcm(audio_np, model.sr, dest)

        size = dest.stat().st_size
        if size < MIN_VALID_BYTES:
            dest.unlink(missing_ok=True)
            raise RuntimeError(
                f"Chatterbox output too small ({size} bytes) for {dest.name} "
                f"— likely a silent/empty generation."
            )
