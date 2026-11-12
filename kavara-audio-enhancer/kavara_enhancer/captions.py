"""Burned-in captions: short readable chunks rendered with one fixed house style (ASS + libass).

Times come from the re-mapped transcript (``timeline.remap_words``), so the captions are
already on the edited timeline and are drawn in the same FFmpeg pass as the final encode.
"""

from __future__ import annotations

import re
from pathlib import Path

from .constants import (
    CAPTION_BREAK_GAP_SECONDS, CAPTION_FONT, CAPTION_HOLD_SECONDS, CAPTION_MAX_CHARS_LANDSCAPE,
    CAPTION_MAX_CHARS_PORTRAIT, CAPTION_MAX_SECONDS, CAPTION_MAX_WORDS, CAPTION_MIN_SECONDS,
)
from .models import SubtitleEntry, TimedWord

_SENTENCE_END = (".", "?", "!")
_CLAUSE_END = (",", ";", ":")


def build_caption_chunks(words: list[TimedWord], portrait: bool = False) -> list[SubtitleEntry]:
    """Group words into short on-screen chunks (a few words at a time, never overlapping)."""
    max_chars = CAPTION_MAX_CHARS_PORTRAIT if portrait else CAPTION_MAX_CHARS_LANDSCAPE
    chunks: list[list[TimedWord]] = []
    line: list[TimedWord] = []

    def flush() -> None:
        if line:
            chunks.append(list(line))
            line.clear()

    for word in words:
        text = word.text.strip()
        if not text:
            continue
        if line:
            chars = len(" ".join(w.text for w in line)) + 1 + len(text)
            gap = word.start_time - line[-1].end_time
            if (
                len(line) >= CAPTION_MAX_WORDS
                or chars > max_chars
                or word.end_time - line[0].start_time > CAPTION_MAX_SECONDS
                or gap > CAPTION_BREAK_GAP_SECONDS
            ):
                flush()
        line.append(TimedWord(text, word.start_time, word.end_time))
        # Break after a sentence end, or after a comma once the chunk is reasonably full.
        if text.endswith(_SENTENCE_END) or (text.endswith(_CLAUSE_END) and len(line) >= 3):
            flush()
    flush()

    entries: list[SubtitleEntry] = []
    for index, chunk in enumerate(chunks):
        start = chunk[0].start_time
        end = max(chunk[-1].end_time + CAPTION_HOLD_SECONDS, start + CAPTION_MIN_SECONDS)
        if index + 1 < len(chunks):
            end = min(end, chunks[index + 1][0].start_time)  # never overlap the next chunk
        if end <= start:
            continue
        entries.append(SubtitleEntry(len(entries) + 1, start, end, " ".join(w.text for w in chunk)))
    return entries


def _ass_time(seconds: float) -> str:
    centis = max(0, int(round(seconds * 100)))
    return f"{centis // 360000}:{centis // 6000 % 60:02d}:{centis // 100 % 60:02d}.{centis % 100:02d}"


def _ass_text(text: str) -> str:
    """Escape characters that ASS treats as override codes."""
    text = text.replace("\\", "").replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", text).strip()


def render_ass(entries: list[SubtitleEntry], width: int, height: int) -> str:
    """Render captions as an ASS file sized to the video, so font and margins scale with it."""
    portrait = height > width
    font_size = round(min(width, height) * 0.048)
    margin_v = round(height * (0.18 if portrait else 0.07))  # portrait: stay clear of Shorts/Reels UI
    margin_h = round(width * 0.06)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # White bold text on a semi-transparent dark box: readable over any screen content.
        f"Style: Default,{CAPTION_FONT},{font_size},&H00FFFFFF,&H00FFFFFF,&H66000000,&H66000000,"
        f"-1,0,0,0,100,100,0,0,3,{max(2, round(font_size * 0.18))},0,2,{margin_h},{margin_h},{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for entry in entries:
        lines.append(
            f"Dialogue: 0,{_ass_time(entry.start_time)},{_ass_time(entry.end_time)},Default,,0,0,0,,"
            f"{_ass_text(entry.text)}"
        )
    return "\n".join(lines) + "\n"


def write_caption_file(
    words: list[TimedWord], width: int, height: int, directory: str,
) -> tuple[Path, int]:
    """Write ``captions.ass`` into ``directory``; returns (path, number of caption chunks)."""
    entries = build_caption_chunks(words, portrait=height > width)
    path = Path(directory) / "captions.ass"
    path.write_text(render_ass(entries, width, height), encoding="utf-8")
    return path, len(entries)


def ass_filter(ass_path: Path) -> str:
    """FFmpeg ``ass`` filter text for a file path (escapes the Windows drive colon and quotes)."""
    escaped = str(ass_path).replace("\\", "/").replace("'", r"'\''").replace(":", r"\:")
    return f"ass=filename='{escaped}'"
