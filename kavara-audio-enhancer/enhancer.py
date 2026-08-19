"""
Kavara Audio Enhancer -- Interactive CLI audio/video enhancement tool.

Pipeline: Ingest -> Extract -> [AI Cut] -> Denoise -> Time-Stretch -> [Loudnorm] -> [AI Subtitles] -> Output
"""

from __future__ import annotations

import argparse
import concurrent.futures
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import colorama

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME = "Kavara Audio Enhancer"
VERSION = "1.4.0"

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts"}

MIN_PLAYBACK_SPEED = 0.25
MAX_PLAYBACK_SPEED = 4.0

MIN_LUFS_TARGET = -70.0
MAX_LUFS_TARGET = -5.0

SAMPLE_RATE = 44100  # Hz -- standard CD-quality sample rate

CHUNK_DURATION_SECONDS = 180.0  # 3 minutes per chunk — optimal for AI accuracy & parallel upload
DEFAULT_MAX_WORKERS = 4         # Default number of concurrent worker threads for AI chunk analysis

GEMINI_MODEL_LABEL = "Gemini 3.7 Flash"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

GEMINI_CUT_SYSTEM_INSTRUCTION = (
    "You are an expert audio editing assistant. "
    "Analyze this audio track and identify all filler words "
    "(e.g., 'um', 'uh', 'ah', 'humm', 'like') and periods of absolute silence "
    "lasting longer than 0.5 seconds. "
    "Return a strict JSON object mapping the exact start_time and end_time "
    "in seconds for every segment that should be cut."
)

GEMINI_SUBTITLE_SYSTEM_INSTRUCTION = (
    "You are an expert audio transcription and subtitling assistant. "
    "Transcribe the provided audio into accurate, natural, and properly punctuated synchronized subtitle entries. "
    "Break sentences into concise subtitle lines (3 to 6 seconds each, maximum 10-14 words per line). "
    "For every line, provide exact start_time and end_time in seconds."
)

# Terminal Styling Colors & Formatting (ANSI with Colorama support)
STYLE_HEADER = "\033[1;36m"   # Bold Cyan
STYLE_SUCCESS = "\033[1;32m"  # Bold Green
STYLE_WARNING = "\033[1;33m"  # Bold Yellow
STYLE_ERROR = "\033[1;31m"    # Bold Red
STYLE_ACCENT = "\033[1;35m"   # Bold Magenta
STYLE_BOLD = "\033[1m"        # Bold
STYLE_DIM = "\033[2m"         # Dim
STYLE_RESET = "\033[0m"       # Reset


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class CutSegment:
    """A time range (in seconds) that should be removed from the audio."""

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
    normalize_lufs: Optional[float] = -16.0
    is_video: bool = False
    extract_audio: bool = False
    output_format: Optional[str] = None
    temp_dir: str = ""
    cut_segments: list[CutSegment] = field(default_factory=list)
    subtitle_entries: list[SubtitleEntry] = field(default_factory=list)
    exported_subtitle_files: list[Path] = field(default_factory=list)

    @property
    def output_path(self) -> Path:
        stem = self.input_path.stem
        if self.extract_audio:
            suffix = self.output_format or ".mp3"
        else:
            suffix = self.output_format or self.input_path.suffix
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        return Path.cwd() / f"{stem}_enhanced{suffix}"


# ---------------------------------------------------------------------------
# Terminal UI & Formatting Helpers
# ---------------------------------------------------------------------------

def configure_terminal_environment() -> None:
    """Initialize colorama and configure stdout/stderr to UTF-8 on Windows."""
    colorama.init(autoreset=True)
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def display_header_banner() -> None:
    """Display the application title banner."""
    print(f"\n{STYLE_HEADER}  ╔═════════════════════════════════════════════════════════════╗{STYLE_RESET}")
    print(f"{STYLE_HEADER}  ║                 {STYLE_BOLD}{APP_NAME} v{VERSION}{STYLE_RESET}{STYLE_HEADER}                  ║{STYLE_RESET}")
    print(f"{STYLE_HEADER}  ║   {STYLE_DIM}Denoise • Time-Stretch • Loudnorm • Subtitles • Video{STYLE_RESET}{STYLE_HEADER}     ║{STYLE_RESET}")
    print(f"{STYLE_HEADER}  ╚═════════════════════════════════════════════════════════════╝{STYLE_RESET}")


def log_step(step: int, total: int, message: str) -> None:
    """Print a formatted progress step to the console."""
    step_tag = f"{STYLE_ACCENT}[{step}/{total}]{STYLE_RESET}"
    print(f"\n  {step_tag} {STYLE_BOLD}{message}{STYLE_RESET}")


def format_file_size(size_in_bytes: int) -> str:
    """Format file size in human-readable units (B, KB, MB, GB)."""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    if size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    if size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.1f} MB"
    return f"{size_in_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_duration(seconds: float) -> str:
    """Format seconds into mm:ss or hh:mm:ss string."""
    total_sec = int(round(seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def display_summary_card(ctx: EnhancerContext) -> None:
    """Print a well-formatted summary of the configured enhancement job."""
    input_size = format_file_size(ctx.input_path.stat().st_size) if ctx.input_path.exists() else "N/A"

    if ctx.is_video:
        mode_desc = "Extract Audio Only" if ctx.extract_audio else "Enhance Video (Remux with video)"
    else:
        mode_desc = "Enhance Audio"

    if ctx.denoise_strength > 0.0:
        denoise_desc = f"{STYLE_SUCCESS}Enabled ({int(ctx.denoise_strength * 100)}% Spectral Gating){STYLE_RESET}"
    else:
        denoise_desc = f"{STYLE_DIM}Disabled (Bypassed){STYLE_RESET}"

    if ctx.normalize_lufs is not None:
        lufs_val = f"{ctx.normalize_lufs:.1f} LUFS"
        if ctx.normalize_lufs == -16.0:
            tag = "Podcast Standard"
        elif ctx.normalize_lufs == -14.0:
            tag = "YouTube Standard"
        elif ctx.normalize_lufs == -23.0:
            tag = "Broadcast Standard"
        else:
            tag = "Custom Target"
        norm_desc = f"{STYLE_SUCCESS}Enabled ({lufs_val} - {tag}){STYLE_RESET}"
    else:
        norm_desc = f"{STYLE_DIM}Disabled (Original Dynamics){STYLE_RESET}"

    ai_desc = f"{STYLE_SUCCESS}Enabled ({GEMINI_MODEL_LABEL} - Parallel){STYLE_RESET}" if ctx.use_ai else f"{STYLE_DIM}Disabled{STYLE_RESET}"

    if ctx.generate_subtitles:
        formats_label = ", ".join(fmt.upper() for fmt in ctx.subtitle_formats)
        sub_desc = f"{STYLE_SUCCESS}Enabled ({formats_label} - {GEMINI_MODEL_LABEL}){STYLE_RESET}"
    else:
        sub_desc = f"{STYLE_DIM}Disabled{STYLE_RESET}"

    print(f"\n  {STYLE_HEADER}┌─────────────────────────────────────────────────────────────┐{STYLE_RESET}")
    print(f"  {STYLE_HEADER}│                    JOB CONFIGURATION                        │{STYLE_RESET}")
    print(f"  {STYLE_HEADER}├─────────────────────────────────────────────────────────────┤{STYLE_RESET}")
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}Source File    :{STYLE_RESET} {ctx.input_path.name} {STYLE_DIM}({input_size}){STYLE_RESET}")
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}Process Mode   :{STYLE_RESET} {mode_desc}")
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}Target Output  :{STYLE_RESET} {ctx.output_path.name}")
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}Playback Speed :{STYLE_RESET} {ctx.speed}x (Pitch Preserved)")
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}Noise Reduction:{STYLE_RESET} {denoise_desc}")
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}Normalization  :{STYLE_RESET} {norm_desc}")
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}AI Smart Cuts  :{STYLE_RESET} {ai_desc}")
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}AI Subtitles   :{STYLE_RESET} {sub_desc}")
    print(f"  {STYLE_HEADER}└─────────────────────────────────────────────────────────────┘{STYLE_RESET}")


def display_completion_banner(ctx: EnhancerContext, elapsed_seconds: float) -> None:
    """Display success banner with elapsed time and output file statistics."""
    output_size = format_file_size(ctx.output_path.stat().st_size) if ctx.output_path.is_file() else "N/A"
    print(f"\n{STYLE_SUCCESS}  ╔═════════════════════════════════════════════════════════════╗{STYLE_RESET}")
    print(f"{STYLE_SUCCESS}  ║                ✨ ENHANCEMENT COMPLETE! ✨                 ║{STYLE_RESET}")
    print(f"{STYLE_SUCCESS}  ╚═════════════════════════════════════════════════════════════╝{STYLE_RESET}")
    print(f"    {STYLE_BOLD}Output File  :{STYLE_RESET} {STYLE_SUCCESS}{ctx.output_path}{STYLE_RESET}")
    print(f"    {STYLE_BOLD}File Size    :{STYLE_RESET} {output_size}")
    if ctx.exported_subtitle_files:
        sub_list = ", ".join(f.name for f in ctx.exported_subtitle_files)
        print(f"    {STYLE_BOLD}Subtitles    :{STYLE_RESET} {STYLE_SUCCESS}{sub_list}{STYLE_RESET}")
    print(f"    {STYLE_BOLD}Elapsed Time :{STYLE_RESET} {elapsed_seconds:.1f}s\n")


# ---------------------------------------------------------------------------
# Validation & System Utilities
# ---------------------------------------------------------------------------

def run_ffmpeg(args: list[str], description: str) -> None:
    """Execute an FFmpeg command, raising on failure."""
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"FFmpeg failed during '{description}':\n{exc.stderr.strip()}"
        ) from exc


def verify_ffmpeg_installed() -> None:
    """Ensure FFmpeg is reachable on the system PATH."""
    if not shutil.which("ffmpeg"):
        print(
            f"\n{STYLE_ERROR}[ERROR] FFmpeg is not installed or not found on your PATH.{STYLE_RESET}\n"
            "        Install it from https://ffmpeg.org/download.html\n"
            "        and ensure the 'ffmpeg' binary is accessible from your terminal."
        )
        sys.exit(1)


def is_supported_file(file_path: Path) -> bool:
    """Check if the given path has a supported audio or video extension."""
    ext = file_path.suffix.lower()
    return ext in SUPPORTED_AUDIO_EXTENSIONS or ext in SUPPORTED_VIDEO_EXTENSIONS


def classify_input_file(file_path: Path) -> bool:
    """Return True if the file is a video, False if audio. Exit on unsupported."""
    ext = file_path.suffix.lower()
    if ext in SUPPORTED_VIDEO_EXTENSIONS:
        return True
    if ext in SUPPORTED_AUDIO_EXTENSIONS:
        return False
    print(f"\n{STYLE_ERROR}[ERROR] Unsupported file format: '{ext}'{STYLE_RESET}")
    print(f"        Supported audio: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}")
    print(f"        Supported video: {', '.join(sorted(SUPPORTED_VIDEO_EXTENSIONS))}")
    sys.exit(1)


def get_audio_duration(file_path: str) -> float:
    """Probe the duration of an audio file in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def find_local_media_files(directory: Path = Path(".")) -> list[Path]:
    """Scan the given directory for supported media files, excluding outputs."""
    all_supported_extensions = SUPPORTED_AUDIO_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS
    try:
        files = [
            file_item for file_item in directory.iterdir()
            if file_item.is_file()
            and file_item.suffix.lower() in all_supported_extensions
            and not file_item.stem.endswith("_enhanced")
        ]
        return sorted(files, key=lambda item: item.name.lower())
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Subtitle Formatting & File Exporters
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Interactive CLI Prompts
# ---------------------------------------------------------------------------

def prompt_menu_choice(
    title: str,
    options: list[tuple[str, str]],
    default_key: str = "1",
) -> str:
    """Display a formatted menu and return the validated user choice."""
    print(f"\n  {STYLE_BOLD}{title}{STYLE_RESET}")
    for key, description in options:
        marker = f"{STYLE_ACCENT}[{key}]{STYLE_RESET}"
        print(f"     {marker} {description}")

    valid_keys = {key for key, _ in options}
    while True:
        choice = input(f"  {STYLE_BOLD}>{STYLE_RESET} Your choice [{default_key}]: ").strip()
        if not choice:
            return default_key
        if choice in valid_keys:
            return choice
        print(f"    {STYLE_ERROR}[!] Invalid choice '{choice}'. Enter one of: {', '.join(sorted(valid_keys))}{STYLE_RESET}")


def prompt_for_source_file() -> Path:
    """Interactively ask the user for the source file with local auto-detection."""
    local_files = find_local_media_files()

    print(f"\n  {STYLE_BOLD}📁 Step 1: Select Media File{STYLE_RESET}")
    if local_files:
        print(f"  {STYLE_DIM}Found {len(local_files)} media file(s) in current directory:{STYLE_RESET}")
        for index, file_path in enumerate(local_files, start=1):
            size_string = format_file_size(file_path.stat().st_size)
            media_type = "Video" if file_path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS else "Audio"
            print(f"     {STYLE_ACCENT}[{index}]{STYLE_RESET} {file_path.name} {STYLE_DIM}({media_type}, {size_string}){STYLE_RESET}")
        print(f"     {STYLE_ACCENT}[0]{STYLE_RESET} Enter custom file path or drag & drop...")

        while True:
            raw_input_text = input(f"  {STYLE_BOLD}>{STYLE_RESET} Select a file [1] or enter path: ").strip().strip('"').strip("'")
            if not raw_input_text:
                return local_files[0].resolve()

            if raw_input_text.isdigit():
                numeric_choice = int(raw_input_text)
                if 1 <= numeric_choice <= len(local_files):
                    return local_files[numeric_choice - 1].resolve()
                if numeric_choice == 0:
                    break
                print(f"    {STYLE_ERROR}[!] Option out of range (0-{len(local_files)}).{STYLE_RESET}")
                continue

            candidate_path = Path(raw_input_text).resolve()
            if candidate_path.is_file() and is_supported_file(candidate_path):
                return candidate_path
            if not candidate_path.is_file():
                print(f"    {STYLE_ERROR}[!] File not found: '{raw_input_text}'. Please try again.{STYLE_RESET}")
            else:
                print(f"    {STYLE_ERROR}[!] Unsupported file format: '{candidate_path.suffix}'.{STYLE_RESET}")

    while True:
        raw_path = input(f"  {STYLE_BOLD}>{STYLE_RESET} Enter path to audio/video file: ").strip().strip('"').strip("'")
        if not raw_path:
            continue
        candidate = Path(raw_path).resolve()
        if not candidate.is_file():
            print(f"    {STYLE_ERROR}[!] File not found: '{raw_path}'. Please check the path and try again.{STYLE_RESET}")
            continue
        if not is_supported_file(candidate):
            print(f"    {STYLE_ERROR}[!] Unsupported format: '{candidate.suffix}'.{STYLE_RESET}")
            print(f"        Supported: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS))}")
            continue
        return candidate


def prompt_for_output_mode(is_video: bool) -> bool:
    """Ask user whether to enhance video container or extract audio only."""
    if not is_video:
        return False

    options = [
        ("1", "Enhance Video (Denoise, time-stretch, and remux with video)"),
        ("2", "Extract Audio Only (Convert video to standalone enhanced audio file)"),
    ]
    choice = prompt_menu_choice("🎬 Step 2: Choose Output Mode", options, default_key="1")
    return choice == "2"


def prompt_for_audio_format(default_extension: str) -> str:
    """Interactively ask user for the desired audio output format."""
    if not default_extension.startswith("."):
        default_extension = f".{default_extension}"

    options = [
        ("1", "MP3  (.mp3)  - Recommended for podcasts & universal playback"),
        ("2", "WAV  (.wav)  - Uncompressed 16-bit PCM (CD quality)"),
        ("3", "AAC  (.aac)  - High-efficiency modern AAC compression"),
        ("4", "FLAC (.flac) - Lossless compressed audio"),
        ("5", f"Match Source ({default_extension})"),
    ]
    choice = prompt_menu_choice("🎵 Step 3: Select Audio Output Format", options, default_key="1")
    format_mapping = {
        "1": ".mp3",
        "2": ".wav",
        "3": ".aac",
        "4": ".flac",
        "5": default_extension,
    }
    return format_mapping[choice]


def prompt_for_playback_speed() -> float:
    """Interactively ask user for playback speed with preset and arbitrary multipliers."""
    options = [
        ("1", "1.0x  - Normal Speed (Natural speech)"),
        ("2", "1.25x - Slight Boost (125% speed)"),
        ("3", "1.5x  - Fast Speed (150% speed - Recommended for podcasts & lectures)"),
        ("4", "1.75x - Very Fast (175% speed)"),
        ("5", "2.0x  - Double Speed (200% speed - Maximum time saving)"),
        ("6", "Custom multiplier (e.g. 1.15x, 1.35x, 0.85x)"),
    ]
    print(f"\n  {STYLE_BOLD}⏩ Step 4: Select Playback Speed{STYLE_RESET}")
    for key, description in options:
        marker = f"{STYLE_ACCENT}[{key}]{STYLE_RESET}"
        print(f"     {marker} {description}")

    speed_presets = {"1": 1.0, "2": 1.25, "3": 1.5, "4": 1.75, "5": 2.0}

    while True:
        user_input = input(f"  {STYLE_BOLD}>{STYLE_RESET} Your choice or speed [3]: ").strip().rstrip("xX")
        if not user_input:
            return 1.5

        if user_input in speed_presets:
            return speed_presets[user_input]

        if user_input == "6":
            while True:
                custom_raw = input(f"  {STYLE_BOLD}>{STYLE_RESET} Enter custom speed ({MIN_PLAYBACK_SPEED}x - {MAX_PLAYBACK_SPEED}x): ").strip().rstrip("xX")
                try:
                    speed_val = float(custom_raw)
                    if MIN_PLAYBACK_SPEED <= speed_val <= MAX_PLAYBACK_SPEED:
                        return round(speed_val, 2)
                    print(f"    {STYLE_ERROR}[!] Speed must be between {MIN_PLAYBACK_SPEED} and {MAX_PLAYBACK_SPEED}.{STYLE_RESET}")
                except ValueError:
                    print(f"    {STYLE_ERROR}[!] Invalid numeric value '{custom_raw}'.{STYLE_RESET}")

        try:
            speed_val = float(user_input)
            if MIN_PLAYBACK_SPEED <= speed_val <= MAX_PLAYBACK_SPEED:
                return round(speed_val, 2)
            print(f"    {STYLE_ERROR}[!] Speed must be between {MIN_PLAYBACK_SPEED} and {MAX_PLAYBACK_SPEED}.{STYLE_RESET}")
        except ValueError:
            print(f"    {STYLE_ERROR}[!] Invalid choice or speed value '{user_input}'. Enter 1-6 or a speed number.{STYLE_RESET}")


def prompt_for_denoise_strength() -> float:
    """Interactively ask user for background noise reduction aggressiveness."""
    options = [
        ("1", "Standard   (80% - Recommended, balanced hiss removal & natural voice)"),
        ("2", "Moderate   (60% - Light noise gating, preserves room ambiance)"),
        ("3", "Aggressive (95% - Heavy noise removal for AC hum or noisy rooms)"),
        ("4", "Custom percentage (0% - 100%)"),
        ("5", "Off        (0% - Bypass noise reduction)"),
    ]
    print(f"\n  {STYLE_BOLD}🎙️  Step 5: Background Noise Reduction Intensity{STYLE_RESET}")
    for key, description in options:
        marker = f"{STYLE_ACCENT}[{key}]{STYLE_RESET}"
        print(f"     {marker} {description}")

    preset_map = {"1": 0.80, "2": 0.60, "3": 0.95, "5": 0.0}

    while True:
        user_input = input(f"  {STYLE_BOLD}>{STYLE_RESET} Your choice [1]: ").strip().rstrip("%")
        if not user_input:
            return 0.80

        if user_input in preset_map:
            return preset_map[user_input]

        if user_input == "4":
            while True:
                custom_raw = input(f"  {STYLE_BOLD}>{STYLE_RESET} Enter noise reduction percentage (0 - 100): ").strip().rstrip("%")
                try:
                    percent_val = float(custom_raw)
                    if 0 <= percent_val <= 100:
                        return round(percent_val / 100.0, 2)
                    print(f"    {STYLE_ERROR}[!] Percentage must be between 0 and 100.{STYLE_RESET}")
                except ValueError:
                    print(f"    {STYLE_ERROR}[!] Invalid numeric value '{custom_raw}'.{STYLE_RESET}")

        try:
            val = float(user_input)
            if 0 <= val <= 1.0:
                return round(val, 2)
            if 1.0 < val <= 100.0:
                return round(val / 100.0, 2)
            print(f"    {STYLE_ERROR}[!] Denoise strength must be between 0% and 100%.{STYLE_RESET}")
        except ValueError:
            print(f"    {STYLE_ERROR}[!] Invalid choice '{user_input}'. Enter 1-5 or a percentage.{STYLE_RESET}")


def prompt_for_loudness_normalization(is_video: bool) -> Optional[float]:
    """Interactively ask user for EBU R128 loudness normalization target."""
    default_key = "2" if is_video else "1"
    options = [
        ("1", "Podcast Standard  (-16.0 LUFS, -1.5 dBTP - Industry standard for spoken word)"),
        ("2", "YouTube / Video   (-14.0 LUFS, -1.0 dBTP - Optimized for YouTube & web video)"),
        ("3", "Broadcast TV      (-23.0 LUFS, -1.0 dBTP - European EBU R128 TV standard)"),
        ("4", "Custom Target     (Specify arbitrary target LUFS e.g. -18.0)"),
        ("5", "Off               (Preserve original dynamic range & volume)"),
    ]
    print(f"\n  {STYLE_BOLD}🔊 Step 6: Audio Volume & Loudness Normalization (EBU R128){STYLE_RESET}")
    for key, description in options:
        marker = f"{STYLE_ACCENT}[{key}]{STYLE_RESET}"
        print(f"     {marker} {description}")

    preset_map: dict[str, Optional[float]] = {
        "1": -16.0,
        "2": -14.0,
        "3": -23.0,
        "5": None,
    }

    while True:
        user_input = input(f"  {STYLE_BOLD}>{STYLE_RESET} Your choice [{default_key}]: ").strip().rstrip("LUFSlufs ")
        if not user_input:
            return preset_map[default_key]

        if user_input in preset_map:
            return preset_map[user_input]

        if user_input == "4":
            while True:
                custom_raw = input(f"  {STYLE_BOLD}>{STYLE_RESET} Enter target LUFS ({MIN_LUFS_TARGET} to {MAX_LUFS_TARGET}): ").strip().rstrip("LUFSlufs ")
                try:
                    lufs_val = float(custom_raw)
                    if lufs_val > 0:
                        lufs_val = -lufs_val
                    if MIN_LUFS_TARGET <= lufs_val <= MAX_LUFS_TARGET:
                        return round(lufs_val, 1)
                    print(f"    {STYLE_ERROR}[!] Target LUFS must be between {MIN_LUFS_TARGET} and {MAX_LUFS_TARGET}.{STYLE_RESET}")
                except ValueError:
                    print(f"    {STYLE_ERROR}[!] Invalid numeric value '{custom_raw}'.{STYLE_RESET}")

        try:
            lufs_val = float(user_input)
            if lufs_val > 0:
                lufs_val = -lufs_val
            if MIN_LUFS_TARGET <= lufs_val <= MAX_LUFS_TARGET:
                return round(lufs_val, 1)
            print(f"    {STYLE_ERROR}[!] Target LUFS must be between {MIN_LUFS_TARGET} and {MAX_LUFS_TARGET}.{STYLE_RESET}")
        except ValueError:
            print(f"    {STYLE_ERROR}[!] Invalid choice '{user_input}'. Enter 1-5 or target LUFS.{STYLE_RESET}")


def prompt_for_subtitle_formats() -> list[str]:
    """Interactively ask user which subtitle/caption formats to export."""
    options = [
        ("1", "SRT  (.srt) - Universal subtitle format (VLC, YouTube, Premiere, Final Cut)"),
        ("2", "VTT  (.vtt) - WebVTT format (HTML5 video players & modern web)"),
        ("3", "Both (.srt and .vtt) - Cross-platform video & web captions"),
        ("4", "All  (.srt, .vtt, and .txt transcript)"),
    ]
    choice = prompt_menu_choice("📝 Select Subtitle & Caption Export Format", options, default_key="1")
    mapping = {
        "1": ["srt"],
        "2": ["vtt"],
        "3": ["srt", "vtt"],
        "4": ["srt", "vtt", "txt"],
    }
    return mapping.get(choice, ["srt"])


def prompt_for_ai_and_subtitles() -> tuple[bool, bool, list[str]]:
    """Ask user whether to enable AI smart cutting, subtitle generation, or both."""
    options = [
        ("1", "No AI Features          - Fast local DSP only"),
        ("2", f"AI Smart Cuts Only      - {GEMINI_MODEL_LABEL} cuts 'um', 'uh', & dead silence"),
        ("3", f"AI Subtitles Only       - {GEMINI_MODEL_LABEL} generates synchronized captions (.srt/.vtt)"),
        ("4", f"Both AI Cuts & Subtitles- Smart silence cuts + synchronized subtitle files"),
    ]
    choice = prompt_menu_choice(f"🤖 Step 7: AI Smart Cuts & Caption Generation ({GEMINI_MODEL_LABEL})", options, default_key="1")

    use_cuts = choice in ("2", "4")
    use_subtitles = choice in ("3", "4")
    subtitle_formats = ["srt"]

    if use_subtitles:
        subtitle_formats = prompt_for_subtitle_formats()

    return use_cuts, use_subtitles, subtitle_formats


def ensure_gemini_api_key() -> bool:
    """Verify GEMINI_API_KEY environment variable or prompt user to enter one."""
    if os.environ.get("GEMINI_API_KEY"):
        return True

    print(f"\n  {STYLE_WARNING}[!] GEMINI_API_KEY environment variable is not set.{STYLE_RESET}")
    print(f"      {GEMINI_MODEL_LABEL} requires an API key for smart cutting & subtitle generation.")
    api_key_input = input(f"  {STYLE_BOLD}>{STYLE_RESET} Paste your Gemini API Key (or press Enter to skip AI): ").strip()
    if api_key_input:
        os.environ["GEMINI_API_KEY"] = api_key_input
        print(f"    {STYLE_SUCCESS}[OK] API Key configured for this session.{STYLE_RESET}")
        return True

    print(f"    {STYLE_DIM}Skipping AI features — proceeding with local DSP only.{STYLE_RESET}")
    return False


def prompt_for_job_confirmation(ctx: EnhancerContext) -> bool:
    """Display summary of pending enhancement job and confirm execution."""
    display_summary_card(ctx)
    while True:
        response = input(f"\n  {STYLE_BOLD}Start enhancement? [Y/n]: {STYLE_RESET}").strip().lower()
        if response in ("", "y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print(f"    {STYLE_ERROR}[!] Please enter 'y' to start or 'n' to cancel.{STYLE_RESET}")


# ---------------------------------------------------------------------------
# Pipeline Stages
# ---------------------------------------------------------------------------

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


def change_speed_preserve_pitch(input_wav: str, output_wav: str, speed: float) -> None:
    """Time-stretch audio by the given factor without altering pitch.

    Uses librosa's phase-vocoder based time_stretch which preserves
    pitch by operating in the STFT domain.
    """
    if speed == 1.0:
        shutil.copy2(input_wav, output_wav)
        return

    import librosa
    import soundfile as sf

    audio_data, sample_rate = librosa.load(input_wav, sr=None, mono=True)
    stretched = librosa.effects.time_stretch(audio_data, rate=speed)
    sf.write(output_wav, stretched, sample_rate)


def normalize_audio_loudness(input_wav: str, output_wav: str, target_lufs: float) -> None:
    """Normalize audio loudness according to the EBU R128 standard."""
    loudnorm_filter = f"loudnorm=I={target_lufs:.1f}:TP=-1.5:LRA=11"
    run_ffmpeg(
        ["-i", input_wav, "-af", loudnorm_filter, "-acodec", "pcm_s16le", output_wav],
        description=f"EBU R128 loudness normalization ({target_lufs:.1f} LUFS)",
    )


# ---------------------------------------------------------------------------
# Gemini AI Engine (Parallel Chunked Processing for Cuts & Subtitles)
# ---------------------------------------------------------------------------

def create_analysis_payload(input_wav: str, temp_dir: str, filename_prefix: str = "analysis_payload") -> str:
    """Compress the WAV down to a small 64 kbps MP3 for fast upload to Gemini."""
    mp3_path = os.path.join(temp_dir, f"{filename_prefix}.mp3")
    run_ffmpeg(
        ["-i", input_wav, "-b:a", "64k", "-ar", "16000", "-ac", "1", mp3_path],
        description="analysis payload compression",
    )
    return mp3_path


def split_audio_into_chunks(
    mp3_path: str,
    temp_dir: str,
    chunk_duration_seconds: float = CHUNK_DURATION_SECONDS,
) -> list[tuple[str, float, float]]:
    """Split an MP3 into temporal chunks for reliable and fast parallel AI analysis."""
    total_duration = get_audio_duration(mp3_path)
    if total_duration <= chunk_duration_seconds:
        return [(mp3_path, 0.0, total_duration)]

    chunks: list[tuple[str, float, float]] = []
    num_chunks = math.ceil(total_duration / chunk_duration_seconds)
    chunks_dir = os.path.join(temp_dir, "ai_chunks")
    os.makedirs(chunks_dir, exist_ok=True)

    for i in range(num_chunks):
        start_time = i * chunk_duration_seconds
        remaining = total_duration - start_time
        duration = min(chunk_duration_seconds, remaining)
        if duration <= 0.5:
            break
        chunk_file = os.path.join(chunks_dir, f"chunk_{i:03d}.mp3")
        run_ffmpeg(
            ["-ss", f"{start_time:.3f}", "-i", mp3_path, "-t", f"{duration:.3f}",
             "-c:a", "libmp3lame", "-b:a", "64k", "-ar", "16000", "-ac", "1", chunk_file],
            description=f"audio chunk extraction [{i+1}/{num_chunks}]",
        )
        chunks.append((chunk_file, start_time, duration))

    return chunks or [(mp3_path, 0.0, total_duration)]


def _build_gemini_cut_schema():
    """Return the Pydantic-based schema class for Gemini cut segments output."""
    from pydantic import BaseModel

    class Segment(BaseModel):
        start_time: float
        end_time: float
        label: str

    class CutAnalysisResult(BaseModel):
        segments_to_cut: list[Segment]

    return CutAnalysisResult


def _build_gemini_subtitle_schema():
    """Return the Pydantic-based schema class for Gemini synchronized subtitles output."""
    from pydantic import BaseModel

    class SubtitleLine(BaseModel):
        start_time: float
        end_time: float
        text: str

    class SubtitleAnalysisResult(BaseModel):
        subtitles: list[SubtitleLine]

    return SubtitleAnalysisResult


def _process_cut_chunk(
    client,
    model_name: str,
    cut_schema,
    chunk_index: int,
    total_chunks: int,
    chunk_path: str,
    offset_seconds: float,
    duration_seconds: float,
) -> tuple[int, list[CutSegment]]:
    """Worker function to upload and analyze a single audio chunk for filler words & silence."""
    start_str = format_duration(offset_seconds)
    end_str = format_duration(offset_seconds + duration_seconds)
    chunk_label = f"[{chunk_index}/{total_chunks}]" if total_chunks > 1 else ""

    print(f"    {STYLE_DIM}>> Analyzing smart cuts chunk {chunk_label} ({start_str} - {end_str}) with {GEMINI_MODEL_LABEL}...{STYLE_RESET}")

    uploaded_file = client.files.upload(file=chunk_path)
    cuts_for_chunk: list[CutSegment] = []

    try:
        from google.genai import types

        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=uploaded_file.uri,
                            mime_type=uploaded_file.mime_type or "audio/mp3",
                        ),
                        types.Part.from_text(
                            text=(
                                "Analyze this audio. Identify all filler words and "
                                "silence periods longer than 0.5 seconds. Return the "
                                "timestamps of segments to cut."
                            )
                        ),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=GEMINI_CUT_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=cut_schema,
            ),
        )

        result = cut_schema.model_validate_json(response.text)

        for seg in result.segments_to_cut:
            adjusted_start = round(seg.start_time + offset_seconds, 3)
            adjusted_end = round(seg.end_time + offset_seconds, 3)
            cuts_for_chunk.append(CutSegment(start_time=adjusted_start, end_time=adjusted_end))

        if total_chunks > 1:
            print(f"    {STYLE_SUCCESS}[OK] Chunk {chunk_label} processed ({len(cuts_for_chunk)} segment(s) to cut).{STYLE_RESET}")

    finally:
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass

    return chunk_index, cuts_for_chunk


def analyze_audio_with_gemini(
    mp3_path: str,
    temp_dir: str,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> list[CutSegment]:
    """Upload and analyze audio using parallel Gemini workers across temporal chunks."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")

    from google import genai

    client = genai.Client(api_key=api_key)
    CutAnalysisResult = _build_gemini_cut_schema()
    model_name = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    chunks = split_audio_into_chunks(mp3_path, temp_dir)
    total_chunks = len(chunks)

    if total_chunks == 1:
        chunk_path, offset, duration = chunks[0]
        _, single_result = _process_cut_chunk(
            client=client,
            model_name=model_name,
            cut_schema=CutAnalysisResult,
            chunk_index=1,
            total_chunks=1,
            chunk_path=chunk_path,
            offset_seconds=offset,
            duration_seconds=duration,
        )
        return single_result

    worker_count = min(total_chunks, max_workers)
    print(f"    {STYLE_DIM}>> Dispatching {total_chunks} chunks across {worker_count} parallel threads with {GEMINI_MODEL_LABEL}...{STYLE_RESET}")

    chunk_results: dict[int, list[CutSegment]] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_index = {
            executor.submit(
                _process_cut_chunk,
                client,
                model_name,
                CutAnalysisResult,
                index,
                total_chunks,
                chunk_path,
                offset,
                duration,
            ): index
            for index, (chunk_path, offset, duration) in enumerate(chunks, start=1)
        }

        for future in concurrent.futures.as_completed(future_to_index):
            chunk_idx = future_to_index[future]
            try:
                processed_idx, cuts = future.result()
                chunk_results[processed_idx] = cuts
            except Exception as exc:
                print(f"    {STYLE_WARNING}[!] Chunk [{chunk_idx}/{total_chunks}] failed: {exc}{STYLE_RESET}")
                chunk_results[chunk_idx] = []

    # Sort all cuts chronologically by chunk order
    all_cuts: list[CutSegment] = []
    for i in range(1, total_chunks + 1):
        all_cuts.extend(chunk_results.get(i, []))

    return all_cuts


def _process_subtitle_chunk(
    client,
    model_name: str,
    subtitle_schema,
    chunk_index: int,
    total_chunks: int,
    chunk_path: str,
    offset_seconds: float,
    duration_seconds: float,
) -> tuple[int, list[tuple[float, float, str]]]:
    """Worker function to upload and transcribe a single audio chunk for subtitles."""
    start_str = format_duration(offset_seconds)
    end_str = format_duration(offset_seconds + duration_seconds)
    chunk_label = f"[{chunk_index}/{total_chunks}]" if total_chunks > 1 else ""

    print(f"    {STYLE_DIM}>> Transcribing subtitles chunk {chunk_label} ({start_str} - {end_str}) with {GEMINI_MODEL_LABEL}...{STYLE_RESET}")

    uploaded_file = client.files.upload(file=chunk_path)
    raw_subtitles: list[tuple[float, float, str]] = []

    try:
        from google.genai import types

        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=uploaded_file.uri,
                            mime_type=uploaded_file.mime_type or "audio/mp3",
                        ),
                        types.Part.from_text(
                            text=(
                                "Transcribe this audio into accurate, synchronized subtitle lines. "
                                "Provide concise 3-6 second subtitle chunks with exact start_time and end_time."
                            )
                        ),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=GEMINI_SUBTITLE_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=subtitle_schema,
            ),
        )

        result = subtitle_schema.model_validate_json(response.text)

        for sub in result.subtitles:
            text = sub.text.strip()
            if not text:
                continue
            adjusted_start = round(sub.start_time + offset_seconds, 3)
            adjusted_end = round(sub.end_time + offset_seconds, 3)
            raw_subtitles.append((adjusted_start, adjusted_end, text))

        if total_chunks > 1:
            print(f"    {STYLE_SUCCESS}[OK] Chunk {chunk_label} transcribed ({len(raw_subtitles)} subtitle lines).{STYLE_RESET}")

    finally:
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass

    return chunk_index, raw_subtitles


def generate_subtitles_with_gemini(
    mp3_path: str,
    temp_dir: str,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> list[SubtitleEntry]:
    """Upload and transcribe audio using parallel Gemini workers across temporal chunks."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")

    from google import genai

    client = genai.Client(api_key=api_key)
    SubtitleAnalysisResult = _build_gemini_subtitle_schema()
    model_name = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    chunks = split_audio_into_chunks(mp3_path, temp_dir)
    total_chunks = len(chunks)

    if total_chunks == 1:
        chunk_path, offset, duration = chunks[0]
        _, raw_subs = _process_subtitle_chunk(
            client=client,
            model_name=model_name,
            subtitle_schema=SubtitleAnalysisResult,
            chunk_index=1,
            total_chunks=1,
            chunk_path=chunk_path,
            offset_seconds=offset,
            duration_seconds=duration,
        )
        return [
            SubtitleEntry(index=idx, start_time=start, end_time=end, text=txt)
            for idx, (start, end, txt) in enumerate(raw_subs, start=1)
        ]

    worker_count = min(total_chunks, max_workers)
    print(f"    {STYLE_DIM}>> Dispatching {total_chunks} chunks across {worker_count} parallel threads with {GEMINI_MODEL_LABEL}...{STYLE_RESET}")

    chunk_results: dict[int, list[tuple[float, float, str]]] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_index = {
            executor.submit(
                _process_subtitle_chunk,
                client,
                model_name,
                SubtitleAnalysisResult,
                index,
                total_chunks,
                chunk_path,
                offset,
                duration,
            ): index
            for index, (chunk_path, offset, duration) in enumerate(chunks, start=1)
        }

        for future in concurrent.futures.as_completed(future_to_index):
            chunk_idx = future_to_index[future]
            try:
                processed_idx, subs = future.result()
                chunk_results[processed_idx] = subs
            except Exception as exc:
                print(f"    {STYLE_WARNING}[!] Chunk [{chunk_idx}/{total_chunks}] transcription failed: {exc}{STYLE_RESET}")
                chunk_results[chunk_idx] = []

    # Assemble and re-index all subtitles in strict chronological order
    all_subtitles: list[SubtitleEntry] = []
    global_index = 1
    for i in range(1, total_chunks + 1):
        for start, end, text in chunk_results.get(i, []):
            all_subtitles.append(
                SubtitleEntry(
                    index=global_index,
                    start_time=start,
                    end_time=end,
                    text=text,
                )
            )
            global_index += 1

    return all_subtitles


# ---------------------------------------------------------------------------
# Smart Cutting Engine
# ---------------------------------------------------------------------------

def _invert_segments(cuts: list[CutSegment], total_duration: float) -> list[tuple[float, float]]:
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


def generate_cut_filter(
    cuts: list[CutSegment],
    total_duration: float,
    video_stream: bool = False,
    audio_stream: bool = True,
    speed_factor: float = 1.0,
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

    Returns
    -------
    str
        The complete -filter_complex filtergraph string.
    """
    keeps = _invert_segments(cuts, total_duration)
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
            filter_parts.append(
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{index}];"
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


# ---------------------------------------------------------------------------
# Final Assembly
# ---------------------------------------------------------------------------

def encode_audio_output(input_wav: str, output_path: Path) -> None:
    """Encode the processed WAV to the target output format."""
    extension = output_path.suffix.lower()

    if extension == ".mp3":
        codec_args = ["-c:a", "libmp3lame", "-b:a", "192k"]
    elif extension in (".aac", ".m4a"):
        codec_args = ["-c:a", "aac", "-b:a", "192k"]
    elif extension == ".flac":
        codec_args = ["-c:a", "flac"]
    elif extension == ".ogg":
        codec_args = ["-c:a", "libvorbis", "-b:a", "192k"]
    elif extension == ".opus":
        codec_args = ["-c:a", "libopus", "-b:a", "128k"]
    elif extension == ".wav":
        codec_args = ["-c:a", "pcm_s16le"]
    else:
        codec_args = ["-c:a", "aac", "-b:a", "192k"]

    run_ffmpeg(
        ["-i", input_wav, *codec_args, str(output_path)],
        description="audio encoding",
    )


def merge_audio_video(
    input_video: Path,
    enhanced_audio_wav: str,
    output_path: Path,
    speed: float,
) -> None:
    """Remux enhanced audio back into original video when no AI video cuts are needed."""
    if speed == 1.0:
        run_ffmpeg(
            ["-i", str(input_video), "-i", enhanced_audio_wav,
             "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0",
             "-c:a", "aac", "-b:a", "192k",
             "-shortest", str(output_path)],
            description="video remuxing (stream copy)",
        )
    else:
        setpts_factor = 1.0 / speed
        run_ffmpeg(
            ["-i", str(input_video), "-i", enhanced_audio_wav,
             "-filter_complex",
             f"[0:v]setpts={setpts_factor:.4f}*PTS[outv]",
             "-map", "[outv]", "-map", "1:a:0",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-c:a", "aac", "-b:a", "192k",
             "-shortest", str(output_path)],
            description="video remuxing (speed adjusted)",
        )


def merge_cut_video_and_audio(
    input_video: Path,
    enhanced_audio_wav: str,
    output_path: Path,
    cuts: list[CutSegment],
    total_duration: float,
    speed: float,
) -> None:
    """Cut and speed-adjust video stream, then mux with enhanced audio in a single pass."""
    filtergraph = generate_cut_filter(
        cuts=cuts,
        total_duration=total_duration,
        video_stream=True,
        audio_stream=False,
        speed_factor=speed,
    )
    run_ffmpeg(
        ["-i", str(input_video), "-i", enhanced_audio_wav,
         "-filter_complex", filtergraph,
         "-map", "[outv]", "-map", "1:a:0",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-c:a", "aac", "-b:a", "192k",
         "-shortest", str(output_path)],
        description="final video assembly with AI cuts",
    )


# ---------------------------------------------------------------------------
# Pipeline Orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(ctx: EnhancerContext) -> None:
    """Execute the full enhancement pipeline."""
    start_time = time.time()

    total_steps = (
        1                                               # Step 1: Extract/Decode audio
        + (1 if ctx.use_ai else 0)                      # AI Cuts
        + (1 if ctx.denoise_strength > 0.0 else 0)      # Noise Reduction
        + (1 if ctx.speed != 1.0 else 0)                # Time-stretching
        + (1 if ctx.normalize_lufs is not None else 0)  # Loudness Normalization
        + (1 if ctx.generate_subtitles else 0)          # AI Subtitle Generation
        + 1                                             # Final Assembly
    )
    current_step = 0

    raw_wav = os.path.join(ctx.temp_dir, "raw_audio.wav")
    cut_wav = os.path.join(ctx.temp_dir, "cut_audio.wav")
    denoised_wav = os.path.join(ctx.temp_dir, "denoised_audio.wav")
    stretched_wav = os.path.join(ctx.temp_dir, "stretched_audio.wav")
    normalized_wav = os.path.join(ctx.temp_dir, "normalized_audio.wav")

    # --- Step 1: Extract / Load Audio ---
    current_step += 1
    if ctx.is_video:
        log_step(current_step, total_steps, "Extracting audio track from video...")
    else:
        log_step(current_step, total_steps, "Loading and decoding audio track...")
    extract_audio(ctx.input_path, raw_wav)
    print(f"    {STYLE_SUCCESS}[OK] Audio extracted successfully.{STYLE_RESET}")

    working_wav = raw_wav

    # --- Step: AI Filler / Silence Detection ---
    if ctx.use_ai:
        current_step += 1
        log_step(current_step, total_steps, f"Running parallel AI filler & silence analysis with {GEMINI_MODEL_LABEL}...")

        mp3_payload = create_analysis_payload(raw_wav, ctx.temp_dir, "cut_analysis_payload")
        ctx.cut_segments = analyze_audio_with_gemini(mp3_payload, ctx.temp_dir, max_workers=ctx.max_workers)

        if ctx.cut_segments:
            print(f"    {STYLE_SUCCESS}[OK] Found {len(ctx.cut_segments)} segment(s) to remove.{STYLE_RESET}")
            duration = get_audio_duration(raw_wav)
            apply_cuts_audio_only(raw_wav, cut_wav, ctx.cut_segments, duration)
            working_wav = cut_wav
        else:
            print(f"    {STYLE_SUCCESS}[OK] No filler words or prolonged silences detected.{STYLE_RESET}")

    # --- Step: Noise Reduction ---
    if ctx.denoise_strength > 0.0:
        current_step += 1
        percentage_label = int(ctx.denoise_strength * 100)
        log_step(current_step, total_steps, f"Reducing background noise ({percentage_label}% spectral gating)...")
        reduce_noise(working_wav, denoised_wav, ctx.denoise_strength)
        print(f"    {STYLE_SUCCESS}[OK] Background noise reduced.{STYLE_RESET}")
        working_wav = denoised_wav

    # --- Step: Time-Stretching ---
    if ctx.speed != 1.0:
        current_step += 1
        log_step(current_step, total_steps, f"Adjusting playback speed to {ctx.speed}x (pitch preserved)...")
        change_speed_preserve_pitch(working_wav, stretched_wav, ctx.speed)
        print(f"    {STYLE_SUCCESS}[OK] Speed adjusted cleanly.{STYLE_RESET}")
        working_wav = stretched_wav

    # --- Step: Loudness Normalization (EBU R128) ---
    if ctx.normalize_lufs is not None:
        current_step += 1
        log_step(current_step, total_steps, f"Normalizing audio loudness to {ctx.normalize_lufs:.1f} LUFS (EBU R128)...")
        normalize_audio_loudness(working_wav, normalized_wav, ctx.normalize_lufs)
        print(f"    {STYLE_SUCCESS}[OK] Loudness normalized to broadcast standard.{STYLE_RESET}")
        working_wav = normalized_wav

    # --- Step: AI Subtitle / Caption Generation ---
    if ctx.generate_subtitles:
        current_step += 1
        log_step(current_step, total_steps, f"Generating synchronized subtitles in parallel with {GEMINI_MODEL_LABEL}...")

        sub_mp3_payload = create_analysis_payload(working_wav, ctx.temp_dir, "subtitle_payload")
        try:
            ctx.subtitle_entries = generate_subtitles_with_gemini(sub_mp3_payload, ctx.temp_dir, max_workers=ctx.max_workers)
            if ctx.subtitle_entries:
                ctx.exported_subtitle_files = save_subtitle_files(
                    ctx.subtitle_entries, ctx.output_path, ctx.subtitle_formats
                )
                print(f"    {STYLE_SUCCESS}[OK] Generated {len(ctx.subtitle_entries)} subtitle lines ({', '.join(ctx.subtitle_formats)}).{STYLE_RESET}")
            else:
                print(f"    {STYLE_WARNING}[!] No speech detected for captioning.{STYLE_RESET}")
        except Exception as sub_err:
            print(f"    {STYLE_WARNING}[!] Subtitle generation warning: {sub_err}{STYLE_RESET}")

    # --- Step: Final Assembly ---
    current_step += 1
    log_step(current_step, total_steps, "Assembling final output file...")

    if ctx.is_video and not ctx.extract_audio:
        duration = get_audio_duration(str(ctx.input_path))
        if ctx.cut_segments:
            merge_cut_video_and_audio(
                input_video=ctx.input_path,
                enhanced_audio_wav=working_wav,
                output_path=ctx.output_path,
                cuts=ctx.cut_segments,
                total_duration=duration,
                speed=ctx.speed,
            )
        else:
            merge_audio_video(
                input_video=ctx.input_path,
                enhanced_audio_wav=working_wav,
                output_path=ctx.output_path,
                speed=ctx.speed,
            )
    else:
        encode_audio_output(working_wav, ctx.output_path)

    elapsed_seconds = time.time() - start_time
    display_completion_banner(ctx, elapsed_seconds)


# ---------------------------------------------------------------------------
# CLI Argument Parser & Configuration Resolver
# ---------------------------------------------------------------------------

def parse_speed_argument(raw_value: str) -> float:
    """Validate and parse CLI speed multiplier argument."""
    try:
        val = float(raw_value.rstrip("xX"))
        if not (MIN_PLAYBACK_SPEED <= val <= MAX_PLAYBACK_SPEED):
            raise argparse.ArgumentTypeError(
                f"Speed must be between {MIN_PLAYBACK_SPEED} and {MAX_PLAYBACK_SPEED} (got {val})."
            )
        return round(val, 2)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid speed value: '{raw_value}'") from exc


def parse_denoise_argument(raw_value: str) -> float:
    """Validate and parse CLI noise reduction argument (percentage or 0.0-1.0 float)."""
    try:
        val = float(raw_value.rstrip("%"))
        if 0.0 <= val <= 1.0:
            return round(val, 2)
        if 1.0 < val <= 100.0:
            return round(val / 100.0, 2)
        raise argparse.ArgumentTypeError(f"Denoise strength must be between 0% and 100% (got {val}).")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid denoise strength: '{raw_value}'") from exc


def parse_lufs_argument(raw_value: str) -> float:
    """Validate and parse CLI loudness target LUFS argument."""
    try:
        val = float(raw_value.rstrip("LUFSlufs "))
        if val > 0:
            val = -val
        if not (MIN_LUFS_TARGET <= val <= MAX_LUFS_TARGET):
            raise argparse.ArgumentTypeError(
                f"Target LUFS must be between {MIN_LUFS_TARGET} and {MAX_LUFS_TARGET} (got {val})."
            )
        return round(val, 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid LUFS value: '{raw_value}'") from exc


def parse_subtitle_format_argument(raw_value: str) -> list[str]:
    """Parse comma-separated or keyword subtitle formats."""
    val = raw_value.strip().lower()
    if val in ("both", "srt,vtt", "vtt,srt"):
        return ["srt", "vtt"]
    if val in ("all", "srt,vtt,txt"):
        return ["srt", "vtt", "txt"]
    if val in ("srt", ".srt"):
        return ["srt"]
    if val in ("vtt", ".vtt"):
        return ["vtt"]
    if val in ("txt", ".txt"):
        return ["txt"]

    parsed = [item.strip().lstrip(".") for item in val.split(",") if item.strip()]
    valid = [item for item in parsed if item in ("srt", "vtt", "txt")]
    return valid or ["srt"]


def build_argument_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser with optional interactive flags."""
    parser = argparse.ArgumentParser(
        prog="kavara-enhancer",
        description=f"{APP_NAME} v{VERSION} — Enhance audio & video files interactively or with flags.",
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Path to the source audio or video file.",
    )
    parser.add_argument(
        "--speed", "-s",
        type=parse_speed_argument,
        help=f"Playback speed multiplier ({MIN_PLAYBACK_SPEED}x to {MAX_PLAYBACK_SPEED}x, e.g. 1.25, 1.5, 1.75).",
    )
    parser.add_argument(
        "--denoise", "--denoise-strength",
        type=parse_denoise_argument,
        dest="denoise_strength",
        help="Noise reduction intensity (0.0 to 1.0 or 0 to 100, e.g. 0.8 or 80%%). Default: 0.8.",
    )
    parser.add_argument(
        "--no-denoise",
        action="store_true",
        default=False,
        help="Disable noise reduction.",
    )
    parser.add_argument(
        "--normalize", "--lufs",
        type=parse_lufs_argument,
        dest="normalize_lufs",
        help="Target loudness in LUFS for EBU R128 volume normalization (e.g. -16.0 for podcasts, -14.0 for YouTube).",
    )
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        default=False,
        help="Disable audio loudness normalization.",
    )
    parser.add_argument(
        "--use-ai",
        action="store_true",
        default=None,
        help=f"Enable {GEMINI_MODEL_LABEL} to detect and cut filler words & silences.",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        default=False,
        help="Disable AI smart cuts explicitly.",
    )
    parser.add_argument(
        "--subtitles", "--captions",
        action="store_true",
        default=None,
        dest="generate_subtitles",
        help=f"Generate synchronized subtitle/caption files using {GEMINI_MODEL_LABEL}.",
    )
    parser.add_argument(
        "--no-subtitles",
        action="store_true",
        default=False,
        help="Disable subtitle generation explicitly.",
    )
    parser.add_argument(
        "--subtitle-format", "--sub-format",
        type=parse_subtitle_format_argument,
        dest="subtitle_formats",
        help="Subtitle formats to export: srt, vtt, both, or all (default: srt).",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f"Number of parallel worker threads for chunked AI analysis (default: {DEFAULT_MAX_WORKERS}).",
    )
    parser.add_argument(
        "--extract-audio", "-x",
        action="store_true",
        default=False,
        help="Extract and enhance audio only from a video file.",
    )
    parser.add_argument(
        "--format", "-fmt",
        type=str,
        help="Target audio output format (e.g. mp3, wav, flac) when outputting audio.",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        default=False,
        help="Launch the interactive wizard even if some flags are passed.",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"{APP_NAME} v{VERSION}",
    )
    return parser


def resolve_execution_context(args: argparse.Namespace) -> Optional[EnhancerContext]:
    """Resolve pipeline settings using flags and interactive prompts as needed."""
    is_interactive_mode = args.interactive or not args.file

    # Step 1: Input File
    if args.file:
        input_path = Path(args.file).resolve()
        if not input_path.is_file():
            print(f"\n{STYLE_ERROR}[ERROR] File not found: '{input_path}'{STYLE_RESET}")
            sys.exit(1)
        if not is_supported_file(input_path):
            classify_input_file(input_path)
    else:
        input_path = prompt_for_source_file()

    is_video = classify_input_file(input_path)

    # Step 2: Output Mode (Video vs Audio extraction)
    if is_video:
        if args.extract_audio or args.format:
            extract_audio_mode = True
        elif is_interactive_mode:
            extract_audio_mode = prompt_for_output_mode(is_video)
        else:
            extract_audio_mode = False
    else:
        extract_audio_mode = False

    # Step 3: Target Output Format
    if is_video and not extract_audio_mode:
        target_format = input_path.suffix
    else:
        if args.format:
            format_name = args.format.strip().lower()
            if not format_name.startswith("."):
                format_name = f".{format_name}"
            if format_name not in SUPPORTED_AUDIO_EXTENSIONS:
                print(f"\n{STYLE_ERROR}[ERROR] Unsupported audio format: '{format_name}'{STYLE_RESET}")
                print(f"        Supported: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}")
                sys.exit(1)
            target_format = format_name
        elif is_interactive_mode:
            default_format = ".mp3" if is_video else input_path.suffix
            target_format = prompt_for_audio_format(default_format)
        else:
            target_format = ".mp3" if is_video else input_path.suffix

    # Step 4: Playback Speed
    if args.speed is not None:
        playback_speed = args.speed
    elif is_interactive_mode:
        playback_speed = prompt_for_playback_speed()
    else:
        playback_speed = 1.0

    # Step 5: Denoise Intensity
    if args.no_denoise:
        denoise_strength = 0.0
    elif args.denoise_strength is not None:
        denoise_strength = args.denoise_strength
    elif is_interactive_mode:
        denoise_strength = prompt_for_denoise_strength()
    else:
        denoise_strength = 0.80

    # Step 6: Loudness Normalization (EBU R128)
    if args.no_normalize:
        normalize_lufs = None
    elif args.normalize_lufs is not None:
        normalize_lufs = args.normalize_lufs
    elif is_interactive_mode:
        normalize_lufs = prompt_for_loudness_normalization(is_video)
    else:
        normalize_lufs = -14.0 if is_video else -16.0

    # Step 7: AI Cuts & Subtitle Options
    use_ai_cuts = False
    use_subtitles = False
    subtitle_formats = args.subtitle_formats or ["srt"]

    if args.no_ai and args.no_subtitles:
        use_ai_cuts = False
        use_subtitles = False
    elif args.use_ai is not None or args.generate_subtitles is not None:
        use_ai_cuts = bool(args.use_ai)
        use_subtitles = bool(args.generate_subtitles)
    elif is_interactive_mode:
        use_ai_cuts, use_subtitles, subtitle_formats = prompt_for_ai_and_subtitles()
    else:
        use_ai_cuts = False
        use_subtitles = False

    # Check and configure Gemini API key if any AI module is enabled
    if use_ai_cuts or use_subtitles:
        has_api_key = ensure_gemini_api_key()
        if not has_api_key:
            use_ai_cuts = False
            use_subtitles = False

    max_workers = max(1, args.workers) if hasattr(args, "workers") and args.workers else DEFAULT_MAX_WORKERS

    context = EnhancerContext(
        input_path=input_path,
        speed=playback_speed,
        use_ai=use_ai_cuts,
        generate_subtitles=use_subtitles,
        subtitle_formats=subtitle_formats,
        max_workers=max_workers,
        denoise_strength=denoise_strength,
        normalize_lufs=normalize_lufs,
        is_video=is_video,
        extract_audio=extract_audio_mode,
        output_format=target_format,
    )

    if is_interactive_mode:
        confirmed = prompt_for_job_confirmation(context)
        if not confirmed:
            print(f"\n  {STYLE_WARNING}[*] Enhancement aborted by user.{STYLE_RESET}\n")
            return None

    return context


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    """Main application entry point."""
    configure_terminal_environment()
    display_header_banner()
    verify_ffmpeg_installed()

    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        context = resolve_execution_context(args)
        if context is None:
            return

        with tempfile.TemporaryDirectory(prefix="kavara_") as temporary_workspace:
            context.temp_dir = temporary_workspace
            run_pipeline(context)

    except KeyboardInterrupt:
        print(f"\n\n  {STYLE_WARNING}[x] Process cancelled by user. Exiting...{STYLE_RESET}\n")
        sys.exit(0)
    except Exception as error:
        print(f"\n{STYLE_ERROR}[ERROR] {error}{STYLE_RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
