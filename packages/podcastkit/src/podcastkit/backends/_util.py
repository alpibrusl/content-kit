from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def write_mp3_from_pcm(audio: Any, sample_rate: int, dest: Path) -> None:
    """Encode a float32 numpy array (mono) to a stereo 192k MP3 via ffmpeg."""
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is not installed — run: pip install numpy") from exc

    if shutil.which("ffmpeg") is None:
        sys.exit("ERROR: ffmpeg not on PATH. Install it and retry.")

    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "-i",
        "pipe:0",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-ac",
        "2",
        str(dest),
    ]
    subprocess.run(cmd, input=pcm, check=True)
