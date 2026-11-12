"""Smart cutting engine: turn cut segments into FFmpeg filtergraphs."""

from __future__ import annotations

import math

from .constants import DECLICK_FADE_SECONDS, MIN_CUT_SECONDS
from .models import CutSegment
from .system import run_ffmpeg


def sanitize_cuts(
    cuts: list[CutSegment],
    total_duration: float,
    min_cut: float = MIN_CUT_SECONDS,
) -> list[CutSegment]:
    """Validate and normalise raw cut segments (from AI and/or local detection).

    - drops cuts with non-finite or inverted (end <= start) timestamps
    - clamps cuts to the [0, total_duration] range
    - drops cuts shorter than ``min_cut`` seconds
    - merges overlapping or touching cuts and returns them in chronological order
    """
    clamped: list[CutSegment] = []
    for cut in cuts:
        if not (math.isfinite(cut.start_time) and math.isfinite(cut.end_time)):
            continue
        if cut.end_time <= cut.start_time:
            continue
        start = max(0.0, cut.start_time)
        end = min(total_duration, cut.end_time)
        if end - start < min_cut:
            continue
        clamped.append(CutSegment(round(start, 3), round(end, 3)))

    clamped.sort(key=lambda segment: segment.start_time)

    merged: list[CutSegment] = []
    for cut in clamped:
        if merged and cut.start_time <= merged[-1].end_time:
            merged[-1].end_time = max(merged[-1].end_time, cut.end_time)
        else:
            merged.append(CutSegment(cut.start_time, cut.end_time))
    return merged


def total_cut_duration(cuts: list[CutSegment]) -> float:
    """Total seconds removed by already-sanitised (non-overlapping) cuts."""
    return sum(cut.end_time - cut.start_time for cut in cuts)


def invert_segments(cuts: list[CutSegment], total_duration: float) -> list[tuple[float, float]]:
    """Convert a list of segments-to-remove into a list of segments-to-keep."""
    if not cuts:
        return [(0.0, total_duration)]

    sorted_cuts = sorted(cuts, key=lambda segment: segment.start_time)

    merged: list[tuple[float, float]] = []
    current_start = sorted_cuts[0].start_time
    current_end = sorted_cuts[0].end_time
    for segment in sorted_cuts[1:]:
        if segment.start_time <= current_end:
            current_end = max(current_end, segment.end_time)
        else:
            merged.append((current_start, current_end))
            current_start = segment.start_time
            current_end = segment.end_time
    merged.append((current_start, current_end))

    keeps: list[tuple[float, float]] = []
    previous_end = 0.0
    for cut_start, cut_end in merged:
        if previous_end < cut_start:
            keeps.append((previous_end, cut_start))
        previous_end = cut_end
    if previous_end < total_duration:
        keeps.append((previous_end, total_duration))

    return keeps


def _boundary_fades(duration: float, fade_in: bool, fade_out: bool, fade: float) -> str:
    """Return ``,afade=...`` filters for the joined edges of a kept segment."""
    if fade <= 0:
        return ""
    length = min(fade, duration / 2)
    if length <= 0:
        return ""
    parts = ""
    if fade_in:
        parts += f",afade=t=in:st=0:d={length:.3f}"
    if fade_out:
        parts += f",afade=t=out:st={duration - length:.3f}:d={length:.3f}"
    return parts


def generate_cut_filter(
    cuts: list[CutSegment],
    total_duration: float,
    video_stream: bool = False,
    audio_stream: bool = True,
    speed_factor: float = 1.0,
    audio_fade: float = DECLICK_FADE_SECONDS,
) -> str:
    """Build an FFmpeg complex filtergraph that trims out cut segments.

    Parameters
    ----------
    cuts : list[CutSegment]
        Time segments in seconds to remove.
    total_duration : float
        Total duration of the input media in seconds.
    video_stream : bool
        Whether to trim video frames from [0:v].
    audio_stream : bool
        Whether to trim audio samples from [0:a].
    speed_factor : float
        Optional playback speed multiplier to apply to the video PTS after cutting.
    audio_fade : float
        Length in seconds of the fade-out/fade-in applied to audio at each cut
        boundary to prevent clicks. Fades are applied in place (not overlapped),
        so audio length stays identical to the cut video and A/V sync is kept.
        Use 0 to disable.

    Returns
    -------
    str
        The complete -filter_complex filtergraph string.
    """
    keeps = invert_segments(cuts, total_duration)
    if not keeps:
        raise ValueError("AI requested cutting the entire file — nothing to keep.")

    filter_parts: list[str] = []
    video_labels: list[str] = []
    audio_labels: list[str] = []

    for index, (start, end) in enumerate(keeps):
        if video_stream:
            filter_parts.append(
                f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{index}];"
            )
            video_labels.append(f"[v{index}]")

        if audio_stream:
            fades = _boundary_fades(
                duration=end - start,
                fade_in=index > 0,
                fade_out=index < len(keeps) - 1,
                fade=audio_fade,
            )
            filter_parts.append(
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS{fades}[a{index}];"
            )
            audio_labels.append(f"[a{index}]")

    segment_count = len(keeps)

    if video_stream and audio_stream:
        concat_inputs = "".join(f"{video_labels[i]}{audio_labels[i]}" for i in range(segment_count))
        filter_parts.append(f"{concat_inputs}concat=n={segment_count}:v=1:a=1[outv][outa]")
    elif video_stream:
        concat_inputs = "".join(video_labels)
        if speed_factor != 1.0:
            setpts_factor = 1.0 / speed_factor
            filter_parts.append(f"{concat_inputs}concat=n={segment_count}:v=1:a=0[cutv];")
            filter_parts.append(f"[cutv]setpts={setpts_factor:.4f}*PTS[outv]")
        else:
            filter_parts.append(f"{concat_inputs}concat=n={segment_count}:v=1:a=0[outv]")
    elif audio_stream:
        concat_inputs = "".join(audio_labels)
        filter_parts.append(f"{concat_inputs}concat=n={segment_count}:v=0:a=1[outa]")

    return "".join(filter_parts)


def apply_cuts_audio_only(
    input_wav: str,
    output_wav: str,
    cuts: list[CutSegment],
    total_duration: float,
) -> None:
    """Remove the cut segments from an audio-only file."""
    filtergraph = generate_cut_filter(
        cuts=cuts,
        total_duration=total_duration,
        video_stream=False,
        audio_stream=True,
    )
    run_ffmpeg(
        ["-i", input_wav, "-filter_complex", filtergraph,
         "-map", "[outa]", "-acodec", "pcm_s16le", output_wav],
        description="AI audio cuts",
    )
