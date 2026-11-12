"""Local (free, offline) silence detection via FFmpeg's ``silencedetect`` filter."""

from __future__ import annotations

import re

from .constants import (
    DEFAULT_SILENCE_THRESHOLD_DB,
    MIN_CUT_SECONDS,
    SILENCE_KEEP_PADDING,
    SILENCE_MIN_DURATION,
)
from .models import CutSegment
from .system import run_ffmpeg

_START_RE = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_END_RE = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")


def parse_silencedetect(ffmpeg_stderr: str, total_duration: float) -> list[tuple[float, float]]:
    """Parse ``silencedetect`` log output into (start, end) silence intervals.

    A silence that runs to the end of the file has a start but no end line; it is
    closed at ``total_duration``.
    """
    intervals: list[tuple[float, float]] = []
    open_start: float | None = None

    for line in ffmpeg_stderr.splitlines():
        end_match = _END_RE.search(line)
        if end_match and open_start is not None:
            intervals.append((open_start, float(end_match.group(1))))
            open_start = None
            continue
        start_match = _START_RE.search(line)
        if start_match:
            open_start = max(0.0, float(start_match.group(1)))

    if open_start is not None and open_start < total_duration:
        intervals.append((open_start, total_duration))
    return intervals


def silences_to_cuts(
    intervals: list[tuple[float, float]],
    padding: float = SILENCE_KEEP_PADDING,
) -> list[CutSegment]:
    """Turn silence intervals into cuts, keeping ``padding`` seconds at each edge."""
    cuts: list[CutSegment] = []
    for start, end in intervals:
        cut_start, cut_end = start + padding, end - padding
        if cut_end - cut_start >= MIN_CUT_SECONDS:
            cuts.append(CutSegment(round(cut_start, 3), round(cut_end, 3)))
    return cuts


def detect_silences(
    input_wav: str,
    total_duration: float,
    threshold_db: float = DEFAULT_SILENCE_THRESHOLD_DB,
    min_duration: float = SILENCE_MIN_DURATION,
    padding: float = SILENCE_KEEP_PADDING,
) -> list[CutSegment]:
    """Find dead-air regions locally and return them as padded cut segments."""
    stderr = run_ffmpeg(
        ["-i", input_wav, "-af", f"silencedetect=noise={threshold_db:g}dB:d={min_duration:g}",
         "-f", "null", "-"],
        description="local silence detection",
        loglevel="info",
    )
    return silences_to_cuts(parse_silencedetect(stderr, total_duration), padding)
