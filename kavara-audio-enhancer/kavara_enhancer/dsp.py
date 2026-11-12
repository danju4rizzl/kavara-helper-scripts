"""Local DSP stages: extraction, denoising, speed change and loudness normalization."""

from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path

from .constants import (
    ATEMPO_MAX_FACTOR,
    ATEMPO_MIN_FACTOR,
    LOUDNORM_LRA,
    LOUDNORM_TRUE_PEAK,
    SAMPLE_RATE,
)
from .system import run_ffmpeg


def extract_audio(input_path: Path, output_wav: str) -> None:
    """Extract the audio track from a media file into a high-quality WAV."""
    run_ffmpeg(
        ["-i", str(input_path), "-vn", "-acodec", "pcm_s16le",
         "-ar", str(SAMPLE_RATE), "-ac", "1", output_wav],
        description="audio extraction",
    )


def reduce_noise(input_wav: str, output_wav: str, denoise_strength: float) -> None:
    """Apply spectral-gated noise reduction to a WAV file with configured intensity."""
    if denoise_strength <= 0.0:
        shutil.copy2(input_wav, output_wav)
        return

    import noisereduce as nr
    import soundfile as sf

    audio_data, sample_rate = sf.read(input_wav)
    reduced = nr.reduce_noise(y=audio_data, sr=sample_rate, prop_decrease=denoise_strength)
    sf.write(output_wav, reduced, sample_rate)


# ---------------------------------------------------------------------------
# Pitch-preserving speed change (FFmpeg atempo)
# ---------------------------------------------------------------------------

def build_atempo_chain(speed: float) -> str:
    """Build an ``atempo`` filter chain for the requested speed multiplier.

    Each ``atempo`` instance is kept within [0.5, 2.0], the range supported by
    every FFmpeg version, by chaining factors multiplicatively (e.g. 4.0x becomes
    ``atempo=2.0,atempo=2.0``).
    """
    if speed <= 0:
        raise ValueError(f"Speed must be positive (got {speed}).")

    factors: list[float] = []
    remaining = speed
    while remaining > ATEMPO_MAX_FACTOR:
        factors.append(ATEMPO_MAX_FACTOR)
        remaining /= ATEMPO_MAX_FACTOR
    while remaining < ATEMPO_MIN_FACTOR:
        factors.append(ATEMPO_MIN_FACTOR)
        remaining /= ATEMPO_MIN_FACTOR
    factors.append(remaining)

    return ",".join(f"atempo={factor:.6g}" for factor in factors)


def change_speed_preserve_pitch(input_wav: str, output_wav: str, speed: float) -> None:
    """Time-stretch audio by the given factor without altering pitch (FFmpeg atempo)."""
    if speed == 1.0:
        shutil.copy2(input_wav, output_wav)
        return

    run_ffmpeg(
        ["-i", input_wav, "-af", build_atempo_chain(speed),
         "-acodec", "pcm_s16le", "-ar", str(SAMPLE_RATE), output_wav],
        description=f"pitch-preserved speed change ({speed}x)",
    )


# ---------------------------------------------------------------------------
# EBU R128 loudness normalization (FFmpeg two-pass loudnorm)
# ---------------------------------------------------------------------------

def build_loudnorm_filter(target_lufs: float, measured: dict[str, float] | None = None) -> str:
    """Build a ``loudnorm`` filter string.

    Without ``measured`` this is the first (analysis) pass or a single-pass
    fallback. With measurements from a first pass it is the second, linear pass.
    """
    base = f"loudnorm=I={target_lufs:.1f}:TP={LOUDNORM_TRUE_PEAK}:LRA={LOUDNORM_LRA:g}"
    if measured is None:
        return base
    return (
        f"{base}"
        f":measured_I={measured['input_i']:.2f}"
        f":measured_TP={measured['input_tp']:.2f}"
        f":measured_LRA={measured['input_lra']:.2f}"
        f":measured_thresh={measured['input_thresh']:.2f}"
        f":offset={measured['target_offset']:.2f}"
        ":linear=true"
    )


def parse_loudnorm_stats(ffmpeg_stderr: str) -> dict[str, float] | None:
    """Extract loudnorm's first-pass JSON statistics from FFmpeg stderr.

    Returns None when no usable measurement exists (e.g. silent audio, where
    FFmpeg reports ``-inf``), so callers can fall back to single-pass mode.
    """
    blocks = re.findall(r"\{[^{}]*\}", ffmpeg_stderr, flags=re.DOTALL)
    if not blocks:
        return None
    try:
        raw = json.loads(blocks[-1])
        stats = {
            key: float(raw[key])
            for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
        }
    except (ValueError, KeyError, TypeError):
        return None

    if not all(math.isfinite(value) for value in stats.values()):
        return None
    return stats


def normalize_audio_loudness(input_wav: str, output_wav: str, target_lufs: float) -> None:
    """Normalize loudness to the EBU R128 target using two-pass loudnorm.

    Pass 1 measures the file; pass 2 applies a precise linear gain. Falls back to
    single-pass (dynamic) normalization if the measurement is unusable.
    """
    first_pass = run_ffmpeg(
        ["-i", input_wav, "-af", f"{build_loudnorm_filter(target_lufs)}:print_format=json",
         "-f", "null", "-"],
        description="loudness analysis (pass 1)",
        loglevel="info",
    )
    measured = parse_loudnorm_stats(first_pass)

    run_ffmpeg(
        ["-i", input_wav, "-af", build_loudnorm_filter(target_lufs, measured),
         "-acodec", "pcm_s16le", "-ar", str(SAMPLE_RATE), output_wav],
        description=f"EBU R128 loudness normalization ({target_lufs:.1f} LUFS)",
    )
