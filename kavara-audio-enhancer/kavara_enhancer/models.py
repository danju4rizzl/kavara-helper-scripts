"""Data models shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .constants import DEFAULT_MAX_WORKERS, DEFAULT_SILENCE_THRESHOLD_DB


@dataclass
class CutSegment:
    """A time range (in seconds) that should be removed from the audio."""

    start_time: float
    end_time: float


@dataclass
class TimedWord:
    """A transcribed word with absolute timestamps (seconds)."""

    text: str
    start_time: float
    end_time: float


@dataclass
class SubtitleEntry:
    """A single timed subtitle entry."""

    index: int
    start_time: float
    end_time: float
    text: str


@dataclass
class EnhancerContext:
    """Holds all configuration and state needed throughout the enhancement pipeline."""

    input_path: Path
    speed: float = 1.0
    use_ai: bool = False
    generate_subtitles: bool = False
    subtitle_formats: list[str] = field(default_factory=lambda: ["srt"])
    max_workers: int = DEFAULT_MAX_WORKERS
    denoise_strength: float = 0.8
    denoise_engine: str = "spectral"
    rnnoise_model: Optional[Path] = None
    normalize_lufs: Optional[float] = -16.0
    is_video: bool = False
    extract_audio: bool = False
    output_format: Optional[str] = None
    cut_silence: bool = False
    silence_threshold_db: float = DEFAULT_SILENCE_THRESHOLD_DB
    dry_run: bool = False
    output_dir: Optional[Path] = None
    output_file: Optional[Path] = None
    temp_dir: str = ""
    cut_segments: list[CutSegment] = field(default_factory=list)
    transcript_words: Optional[list[TimedWord]] = None  # one transcript of the ORIGINAL audio, shared by cuts and subtitles
    transcript_error: Optional[str] = None
    subtitle_entries: list[SubtitleEntry] = field(default_factory=list)
    exported_subtitle_files: list[Path] = field(default_factory=list)

    @property
    def output_path(self) -> Path:
        if self.output_file is not None:
            return self.output_file
        stem = self.input_path.stem
        if self.extract_audio:
            suffix = self.output_format or ".mp3"
        else:
            suffix = self.output_format or self.input_path.suffix
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        return (self.output_dir or Path.cwd()) / f"{stem}_enhanced{suffix}"
