"""FFmpeg execution, media probing and file classification."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .constants import (
    STYLE_ERROR, STYLE_RESET, SUPPORTED_AUDIO_EXTENSIONS, SUPPORTED_VIDEO_EXTENSIONS,
)


FILTER_SCRIPT_THRESHOLD = 8000


def run_ffmpeg(args: list[str], description: str, loglevel: str = "error") -> str:
    """Execute an FFmpeg command, raising on failure. Returns captured stderr."""
    args = list(args)
    script_path: str | None = None
    # Long filtergraphs (hundreds of cuts) exceed the Windows ~32K command-line
    # limit (WinError 206), so pass them via a script file instead.
    for i in range(len(args) - 1):
        if args[i] == "-filter_complex" and len(args[i + 1]) > FILTER_SCRIPT_THRESHOLD:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False, encoding="utf-8"
            ) as handle:
                handle.write(args[i + 1])
                script_path = handle.name
            args[i] = "-filter_complex_script"
            args[i + 1] = script_path
            break

    command = ["ffmpeg", "-hide_banner", "-loglevel", loglevel, "-y", *args]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"FFmpeg failed during '{description}':\n{exc.stderr.strip()}"
        ) from exc
    finally:
        if script_path:
            Path(script_path).unlink(missing_ok=True)
    return result.stderr


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
