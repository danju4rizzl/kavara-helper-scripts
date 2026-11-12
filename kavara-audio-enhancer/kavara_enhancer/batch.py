"""Batch mode: expand inputs (files, globs, folders), derive per-file jobs, summarise results."""

from __future__ import annotations

import dataclasses
import glob
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .constants import SUPPORTED_VIDEO_EXTENSIONS
from .models import EnhancerContext
from .system import is_supported_file
from .ui import format_duration

_GLOB_CHARS = ("*", "?", "[")


def _is_enhancer_output(path: Path) -> bool:
    return path.stem.endswith("_enhanced")


def _sorted_media(paths) -> list[Path]:
    """Supported media files (outputs excluded), sorted by name, case-insensitively."""
    usable = [p for p in paths if p.is_file() and is_supported_file(p) and not _is_enhancer_output(p)]
    return sorted(usable, key=lambda p: (p.name.lower(), str(p)))


def collect_input_files(patterns: list[str]) -> tuple[list[Path], list[str]]:
    """Expand file paths, glob patterns and folders into a de-duplicated file list.

    Returns ``(files, problems)``. Globs and folders skip previous ``*_enhanced``
    outputs; a file named explicitly is always honoured if its format is supported.
    The shell does not expand globs on Windows, so this does it for every platform.
    """
    files: list[Path] = []
    problems: list[str] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        resolved = path.resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            files.append(resolved)

    for raw in patterns:
        cleaned = raw.strip().strip('"').strip("'")
        path = Path(cleaned).expanduser()

        if path.is_file():
            if is_supported_file(path):
                add(path)
            else:
                problems.append(f"Unsupported file format '{path.suffix}': {raw}")
        elif path.is_dir():
            found = _sorted_media(path.iterdir())
            if not found:
                problems.append(f"No supported media files in folder: {raw}")
            for item in found:
                add(item)
        elif any(char in cleaned for char in _GLOB_CHARS):
            found = _sorted_media(Path(match) for match in glob.glob(os.path.expanduser(cleaned)))
            if not found:
                problems.append(f"No media files match: {raw}")
            for item in found:
                add(item)
        else:
            problems.append(f"File not found: {raw}")

    return files, problems


def derive_file_context(
    template: EnhancerContext,
    path: Path,
    *,
    extract_audio_pref: bool,
    audio_format: Optional[str],
    normalize_is_default: bool,
) -> EnhancerContext:
    """Create the job for another file in a batch from the first file's settings.

    Settings chosen once (speed, denoise, AI, ...) carry over. Things that depend on
    the file type are recomputed: whether it is a video, whether to extract audio,
    the output extension, and the default loudness target when none was chosen.
    """
    is_video = path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
    extract = is_video and extract_audio_pref

    if is_video and not extract:
        output_format = path.suffix
    elif is_video:
        output_format = audio_format or ".mp3"
    else:
        output_format = audio_format or path.suffix

    normalize_lufs = template.normalize_lufs
    if normalize_is_default:
        normalize_lufs = -14.0 if is_video else -16.0

    return dataclasses.replace(
        template,
        input_path=path,
        is_video=is_video,
        extract_audio=extract,
        output_format=output_format,
        normalize_lufs=normalize_lufs,
        output_file=None,
        temp_dir="",
        cut_segments=[],
        subtitle_entries=[],
        exported_subtitle_files=[],
        caption_file=None,
        subtitle_formats=list(template.subtitle_formats),
    )


def find_output_collisions(contexts: list[EnhancerContext]) -> dict[Path, list[Path]]:
    """Outputs that more than one input would write to (same name in different folders)."""
    by_output: dict[str, list[EnhancerContext]] = {}
    for ctx in contexts:
        by_output.setdefault(os.path.normcase(str(ctx.output_path)), []).append(ctx)
    return {
        group[0].output_path: [ctx.input_path for ctx in group]
        for group in by_output.values()
        if len(group) > 1
    }


@dataclass
class BatchResult:
    input_path: Path
    output_path: Path
    success: bool
    seconds: float
    error: Optional[str] = None


def format_batch_summary(results: list[BatchResult]) -> str:
    """Plain-text summary table for the end of a batch run."""
    succeeded = sum(1 for result in results if result.success)
    lines = []
    for result in results:
        status = "OK  " if result.success else "FAIL"
        detail = result.output_path.name if result.success else (result.error or "unknown error").splitlines()[0]
        lines.append(f"{status}  {result.input_path.name}  ->  {detail}  ({format_duration(result.seconds)})")
    lines.append("")
    lines.append(f"{succeeded}/{len(results)} file(s) processed successfully.")
    return "\n".join(lines)
