from __future__ import annotations

import contextlib
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Anchor, EpisodeConfig

TAIL_PAD_SEC = 5.0
SAMPLE_RATE = 44100


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def db(x: float) -> float:
    """Convert dB to linear gain."""
    return 10 ** (x / 20.0)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a shell command, capture output, raise with full stderr on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(f"\nCommand failed: {' '.join(cmd[:6])}...\n")
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return result


def ffprobe_duration(path: Path) -> float:
    """Return the duration of an audio/video file in seconds via ffprobe."""
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(result.stdout.strip())


# ---------------------------------------------------------------------------
# Internal anchor data class (runtime, not config)
# ---------------------------------------------------------------------------


@dataclass
class _LineAnchor:
    start: float
    end: float


def resolve_time(spec: Anchor, anchors: dict[str, _LineAnchor]) -> float:
    """Resolve an Anchor tuple to an absolute timestamp in seconds.

    spec is (line_id, "start"|"end", offset_seconds).
    Returns max(0, base + offset) so negative results are clamped to 0.
    """
    line_id, edge, offset = spec
    a = anchors[line_id]
    base = a.start if edge == "start" else a.end
    return max(0.0, base + offset)


# ---------------------------------------------------------------------------
# Pass 1 — voice track
# ---------------------------------------------------------------------------


def build_voices_track(
    episode_dir: Path,
    config: EpisodeConfig,
    log: Callable[..., None] = print,
) -> dict[str, _LineAnchor]:
    """Concatenate silence + voice pairs into a single WAV (voices_track.wav).

    Returns a mapping of line_id -> _LineAnchor(start, end) in seconds from
    the beginning of the track. A tail-silence pad is appended at the end.
    """
    voices_dir = episode_dir / "voices"
    build_dir = episode_dir / "build"
    voices_track = build_dir / "voices_track.wav"
    timeline = config.timeline

    log(f"Pass 1: building voice track for {len(timeline)} lines")

    inputs: list[str] = []
    filter_parts: list[str] = []
    concat_labels: list[str] = []
    anchors: dict[str, _LineAnchor] = {}
    cursor = 0.0
    next_in = 0

    for idx, entry in enumerate(timeline):
        line_id = entry.id
        pre = entry.pre_silence
        voice_path = voices_dir / f"{line_id}.mp3"

        if not voice_path.exists():
            sys.exit(f"ERROR: missing voice file {voice_path}. Run 'podcastkit generate' first.")

        inputs += ["-f", "lavfi", "-t", f"{pre:.3f}", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=stereo"]
        sil_input_idx = next_in
        next_in += 1
        inputs += ["-i", str(voice_path)]
        voice_input_idx = next_in
        next_in += 1

        sil_lbl = f"s{idx}"
        voice_lbl = f"v{idx}"
        filter_parts.append(
            f"[{sil_input_idx}:a]aresample={SAMPLE_RATE},"
            f"aformat=sample_fmts=s16:channel_layouts=stereo[{sil_lbl}]"
        )
        filter_parts.append(
            f"[{voice_input_idx}:a]aresample={SAMPLE_RATE},"
            f"aformat=sample_fmts=s16:channel_layouts=stereo[{voice_lbl}]"
        )
        concat_labels.append(f"[{sil_lbl}][{voice_lbl}]")

        voice_dur = ffprobe_duration(voice_path)
        start = cursor + pre
        end = start + voice_dur
        anchors[line_id] = _LineAnchor(start=start, end=end)
        cursor = end

    # Trailing silence pad
    inputs += [
        "-f",
        "lavfi",
        "-t",
        f"{TAIL_PAD_SEC:.3f}",
        "-i",
        f"anullsrc=r={SAMPLE_RATE}:cl=stereo",
    ]
    pad_idx = next_in
    next_in += 1
    pad_lbl = "pad"
    filter_parts.append(
        f"[{pad_idx}:a]aresample={SAMPLE_RATE},"
        f"aformat=sample_fmts=s16:channel_layouts=stereo[{pad_lbl}]"
    )
    concat_labels.append(f"[{pad_lbl}]")

    # Each label pair contributes one segment to the concat
    n_streams = sum(c.count("[") for c in concat_labels)

    filter_complex = ";".join(filter_parts) + ";"
    filter_complex += "".join(concat_labels) + f"concat=n={n_streams}:v=0:a=1[out]"

    build_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    cmd += inputs
    cmd += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-c:a",
        "pcm_s16le",
        str(voices_track),
    ]
    run(cmd)

    voices_track_dur = ffprobe_duration(voices_track)
    log(
        f"  voices_track.wav  -> {voices_track_dur:6.2f}s  "
        f"({len(timeline)} lines + {TAIL_PAD_SEC}s tail pad)"
    )
    return anchors


# ---------------------------------------------------------------------------
# Pass 2 — mix overlays
# ---------------------------------------------------------------------------


def mix_overlays(
    episode_dir: Path,
    config: EpisodeConfig,
    anchors: dict[str, _LineAnchor],
    log: Callable[..., None] = print,
) -> None:
    """Mix bg tracks and SFX hits onto voices_track.wav and write the final MP3."""
    build_dir = episode_dir / "build"
    voices_track = build_dir / "voices_track.wav"
    output_path = episode_dir / config.output

    log("Pass 2: mixing ambience, music, and SFX")

    inputs = ["-i", str(voices_track)]
    filter_parts: list[str] = []
    mix_labels = ["[0:a]"]

    available_bg = []
    for bg in config.bg_tracks:
        bg_path = episode_dir / bg.file
        if not bg_path.exists():
            log(f"  ! missing optional bg file, skipping: {bg.file}")
            continue
        available_bg.append((bg, bg_path))

    available_sfx = []
    for sfx in config.sfx_hits:
        sfx_path = episode_dir / sfx.file
        if not sfx_path.exists():
            log(f"  ! missing optional SFX, skipping: {sfx.file}")
            continue
        available_sfx.append((sfx, sfx_path))

    next_input = 1

    for bg, bg_path in available_bg:
        start_t = resolve_time(bg.start, anchors)
        fade_out_t = resolve_time(bg.fade_out_at, anchors)
        fade_out_dur = bg.fade_out_dur
        fade_in_dur = bg.fade_in
        vol = db(bg.volume_db)

        if bg.loop:
            inputs += ["-stream_loop", "-1", "-i", str(bg_path)]
        else:
            inputs += ["-i", str(bg_path)]
        idx = next_input
        next_input += 1

        delay_ms = int(round(start_t * 1000))
        lbl = f"bg{idx}"
        chain = (
            f"[{idx}:a]aresample={SAMPLE_RATE},"
            f"aformat=sample_fmts=s16:channel_layouts=stereo,"
            f"volume={vol:.4f},"
            f"adelay={delay_ms}|{delay_ms},"
            f"afade=t=in:st={start_t:.3f}:d={fade_in_dur:.3f},"
            f"afade=t=out:st={fade_out_t:.3f}:d={fade_out_dur:.3f}"
            f"[{lbl}]"
        )
        filter_parts.append(chain)
        mix_labels.append(f"[{lbl}]")

    for sfx, sfx_path in available_sfx:
        at_t = resolve_time(sfx.at, anchors)
        vol = sfx.volume
        inputs += ["-i", str(sfx_path)]
        idx = next_input
        next_input += 1
        delay_ms = int(round(at_t * 1000))
        lbl = f"fx{idx}"
        chain = (
            f"[{idx}:a]aresample={SAMPLE_RATE},"
            f"aformat=sample_fmts=s16:channel_layouts=stereo,"
            f"volume={vol:.4f},"
            f"adelay={delay_ms}|{delay_ms}"
            f"[{lbl}]"
        )
        filter_parts.append(chain)
        mix_labels.append(f"[{lbl}]")

    n_mix = len(mix_labels)
    filter_complex = ";".join(filter_parts)
    if filter_parts:
        filter_complex += ";"
    filter_complex += "".join(mix_labels) + f"amix=inputs={n_mix}:duration=first:normalize=0[out]"

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    cmd += inputs
    cmd += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        "2",
        str(output_path),
    ]
    run(cmd)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify(output_path: Path, log: Callable[..., None] = print) -> dict[str, Any]:
    """Return duration, size, and loudness info for the assembled output."""
    duration = ffprobe_duration(output_path)
    minutes = int(duration // 60)
    seconds = duration - minutes * 60
    size_mb = output_path.stat().st_size / 1024 / 1024
    log("")
    log(f"Final: {output_path.name}  {minutes}:{seconds:05.2f}  {size_mb:.2f} MB")

    result: dict[str, Any] = {
        "output": output_path.name,
        "duration_s": round(duration, 2),
        "size_mb": round(size_mb, 2),
    }

    # Loudness summary (best-effort; ffmpeg reports numbers in stderr)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(output_path),
            "-af",
            "loudnorm=print_format=summary",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    for line in proc.stderr.splitlines():
        if "Input Integrated" in line:
            log(f"  {line.strip()}")
            with contextlib.suppress(ValueError, IndexError):
                result["integrated_lufs"] = float(line.split()[-2])
        elif "Input True Peak" in line:
            log(f"  {line.strip()}")
            with contextlib.suppress(ValueError, IndexError):
                result["true_peak_dbtp"] = float(line.split()[-2])

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def assemble(
    episode_dir: Path,
    config: EpisodeConfig,
    log: Callable[..., None] = print,
) -> dict[str, Any]:
    """Run the full two-pass assembly pipeline for an episode.

    Pass 1: concatenate voice lines with silence into a WAV track.
    Pass 2: mix in background tracks and SFX hits, encode to MP3.
    Returns a dict with output filename, duration, size, and loudness.
    """
    if shutil.which("ffmpeg") is None:
        sys.exit("ERROR: ffmpeg not on PATH. Install it and retry.")
    if shutil.which("ffprobe") is None:
        sys.exit("ERROR: ffprobe not on PATH. Install it with ffmpeg.")

    anchors = build_voices_track(episode_dir, config, log=log)
    mix_overlays(episode_dir, config, anchors, log=log)
    output_path = episode_dir / config.output
    result = verify(output_path, log=log)
    log("")
    log(f"Done. Open {output_path} to listen.")
    return result
