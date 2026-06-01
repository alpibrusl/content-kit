"""SFX and music generation via HuggingFace Transformers MusicGen.

Requires the 'audiocraft' optional extra:
    pip install "podcastkit[audiocraft]"

Uses facebook/musicgen-* models (no API key, runs locally).
AudioGen SFX models (facebook/audiogen-*) require the audiocraft package
and are not available via transformers — they are supported as a fallback
when audiocraft is installed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, object] = {}

# MusicGen token rate: sr / hop_length = 32000 / 640 = 50 tokens/sec
_TOKENS_PER_SECOND = 50


def _device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def _load_musicgen(model_name: str, device: str):
    key = f"musicgen:{model_name}:{device}"
    if key not in _MODEL_CACHE:
        try:
            from transformers import AutoProcessor, MusicgenForConditionalGeneration
        except ImportError as exc:
            raise RuntimeError(
                "transformers is not installed. "
                "Install it with: pip install 'podcastkit[audiocraft]'"
            ) from exc
        processor = AutoProcessor.from_pretrained(model_name)
        model = MusicgenForConditionalGeneration.from_pretrained(model_name)
        model = model.to(device)
        _MODEL_CACHE[key] = (processor, model)
    return _MODEL_CACHE[key]


def _save_wav(audio_values, sample_rate: int, dest: Path) -> None:
    """Save a [channels, samples] tensor to a WAV file using stdlib wave + numpy."""
    import wave

    import numpy as np

    dest.parent.mkdir(parents=True, exist_ok=True)
    audio_np = audio_values.cpu().float().numpy()  # [channels, samples]
    # Clip and convert to int16 PCM
    audio_int16 = (audio_np * 32767).clip(-32768, 32767).astype(np.int16)
    n_channels = audio_int16.shape[0]
    # Interleave channels: shape → [samples, channels] → flatten
    frames = audio_int16.T.flatten().tobytes()
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(frames)


def _run_musicgen(
    prompt: str,
    dest: Path,
    *,
    duration: float,
    model_name: str,
    device: str | None,
    log: Callable[..., None],
) -> dict:
    effective_device = device or _device()
    log(f"Loading {model_name!r} on {effective_device}…")
    processor, model = _load_musicgen(model_name, effective_device)

    max_new_tokens = int(duration * _TOKENS_PER_SECOND)
    log(f"Generating ({duration}s): {prompt!r}")

    inputs = processor(text=[prompt], padding=True, return_tensors="pt")
    inputs = {k: v.to(effective_device) for k, v in inputs.items()}

    import torch

    with torch.no_grad():
        audio_values = model.generate(**inputs, max_new_tokens=max_new_tokens)

    sr = model.config.audio_encoder.sampling_rate
    _save_wav(audio_values[0], sr, dest)
    log(f"Saved → {dest}")

    return {
        "path": str(dest),
        "duration_s": duration,
        "sample_rate": sr,
        "prompt": prompt,
        "model": model_name,
        "device": effective_device,
    }


def generate_sfx(
    prompt: str,
    dest: Path,
    *,
    duration: float = 3.0,
    model_name: str = "facebook/musicgen-small",
    device: str | None = None,
    log: Callable[..., None] = print,
) -> dict:
    """Generate a sound effect from a text prompt.

    Uses MusicGen (transformers). For best SFX results keep duration ≤ 5s.
    Returns a dict with keys: path, duration_s, sample_rate, prompt, model, device.
    """
    return _run_musicgen(
        prompt, dest, duration=duration, model_name=model_name, device=device, log=log
    )


def generate_music(
    prompt: str,
    dest: Path,
    *,
    duration: float = 30.0,
    model_name: str = "facebook/musicgen-small",
    device: str | None = None,
    log: Callable[..., None] = print,
) -> dict:
    """Generate background music from a text prompt.

    Uses MusicGen (transformers). Returns a dict with keys: path, duration_s,
    sample_rate, prompt, model, device.
    """
    return _run_musicgen(
        prompt, dest, duration=duration, model_name=model_name, device=device, log=log
    )
