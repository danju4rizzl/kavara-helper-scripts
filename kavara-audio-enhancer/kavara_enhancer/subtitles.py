"""Subtitle timestamp formatting and file exporters."""

from __future__ import annotations

from pathlib import Path

from .models import SubtitleEntry


def _split_seconds_to_hms_ms(total_seconds: float) -> tuple[int, int, int, int]:
    """Split seconds into hours, minutes, seconds, and milliseconds."""
    if total_seconds < 0.0:
        total_seconds = 0.0
    total_ms = int(round(total_seconds * 1000))
    hours = total_ms // 3600000
    remaining = total_ms % 3600000
    minutes = remaining // 60000
    remaining %= 60000
    seconds = remaining // 1000
    milliseconds = remaining % 1000
    return hours, minutes, seconds, milliseconds


def format_timestamp_srt(seconds: float) -> str:
    """Format seconds into SubRip timestamp: HH:MM:SS,mmm."""
    h, m, s, ms = _split_seconds_to_hms_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_timestamp_vtt(seconds: float) -> str:
    """Format seconds into WebVTT timestamp: HH:MM:SS.mmm."""
    h, m, s, ms = _split_seconds_to_hms_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def render_srt(entries: list[SubtitleEntry]) -> str:
    """Render subtitle entries in standard SRT syntax."""
    blocks: list[str] = []
    for entry in entries:
        start_formatted = format_timestamp_srt(entry.start_time)
        end_formatted = format_timestamp_srt(entry.end_time)
        blocks.append(f"{entry.index}\n{start_formatted} --> {end_formatted}\n{entry.text}\n")
    return "\n".join(blocks)


def render_vtt(entries: list[SubtitleEntry]) -> str:
    """Render subtitle entries in standard WebVTT syntax."""
    lines: list[str] = ["WEBVTT", ""]
    for entry in entries:
        start_formatted = format_timestamp_vtt(entry.start_time)
        end_formatted = format_timestamp_vtt(entry.end_time)
        lines.append(f"{entry.index}\n{start_formatted} --> {end_formatted}\n{entry.text}\n")
    return "\n".join(lines)


def render_txt(entries: list[SubtitleEntry]) -> str:
    """Render subtitle entries into a clean timestamped text transcript."""
    return "\n".join(f"[{format_timestamp_vtt(entry.start_time)}] {entry.text}" for entry in entries)


def save_subtitle_files(
    entries: list[SubtitleEntry],
    media_output_path: Path,
    formats: list[str],
) -> list[Path]:
    """Export subtitle files matching the output media filename stem."""
    saved_files: list[Path] = []
    stem = media_output_path.stem
    parent_dir = media_output_path.parent

    for fmt in formats:
        fmt_clean = fmt.lower().lstrip(".")
        if fmt_clean == "srt":
            content = render_srt(entries)
            target_path = parent_dir / f"{stem}.srt"
        elif fmt_clean == "vtt":
            content = render_vtt(entries)
            target_path = parent_dir / f"{stem}.vtt"
        elif fmt_clean == "txt":
            content = render_txt(entries)
            target_path = parent_dir / f"{stem}_transcript.txt"
        else:
            continue

        target_path.write_text(content, encoding="utf-8")
        saved_files.append(target_path)

    return saved_files
