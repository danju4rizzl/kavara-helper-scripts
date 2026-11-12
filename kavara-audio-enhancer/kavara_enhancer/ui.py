"""Terminal UI and formatting helpers."""

from __future__ import annotations

import sys

import colorama

from .constants import (
    APP_NAME, GEMINI_MODEL_LABEL, STYLE_ACCENT, STYLE_BOLD, STYLE_DIM,
    STYLE_HEADER, STYLE_RESET, STYLE_SUCCESS, VERSION,
)
from .models import CutSegment, EnhancerContext
from .subtitles import format_timestamp_vtt


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

    if ctx.use_ai or ctx.cut_silence:
        silence_source = "local detection + AI fillers" if ctx.use_ai else "local detection"
        silence_desc = f"{STYLE_SUCCESS}Enabled ({ctx.silence_threshold_db:g} dB, {silence_source}){STYLE_RESET}"
    else:
        silence_desc = f"{STYLE_DIM}Disabled{STYLE_RESET}"

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
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}Target Output  :{STYLE_RESET} {ctx.output_path}")
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}Playback Speed :{STYLE_RESET} {ctx.speed}x (Pitch Preserved)")
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}Noise Reduction:{STYLE_RESET} {denoise_desc}")
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}Normalization  :{STYLE_RESET} {norm_desc}")
    print(f"  {STYLE_HEADER}│{STYLE_RESET}  {STYLE_BOLD}Silence Removal:{STYLE_RESET} {silence_desc}")
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


def format_cut_report(
    cuts: list[CutSegment],
    total_duration: float,
    speed: float = 1.0,
    max_listed: int = 40,
) -> str:
    """Render a human-readable report of the planned cuts (used by --dry-run)."""
    if not cuts:
        return "No cuts planned."

    removed = sum(cut.end_time - cut.start_time for cut in cuts)
    remaining = max(total_duration - removed, 0.0)
    lines = []
    for cut in cuts[:max_listed]:
        length = cut.end_time - cut.start_time
        lines.append(
            f"{format_timestamp_vtt(cut.start_time)} -> {format_timestamp_vtt(cut.end_time)}  ({length:.2f}s)"
        )
    if len(cuts) > max_listed:
        lines.append(f"... and {len(cuts) - max_listed} more")

    percent = (removed / total_duration * 100.0) if total_duration > 0 else 0.0
    lines.append("")
    lines.append(f"{len(cuts)} cut(s) removing {removed:.1f}s of {total_duration:.1f}s ({percent:.1f}%).")
    final = remaining / speed if speed > 0 else remaining
    suffix = f" (after {speed}x speed)" if speed != 1.0 else ""
    lines.append(f"Resulting duration: {format_duration(final)}{suffix}.")
    return "\n".join(lines)
