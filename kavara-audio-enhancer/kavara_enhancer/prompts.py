"""Interactive CLI prompts."""

from __future__ import annotations

import getpass
import os
from pathlib import Path
from typing import Optional

from .constants import (
    MAX_LUFS_TARGET, MAX_PLAYBACK_SPEED, MIN_LUFS_TARGET,
    MIN_PLAYBACK_SPEED, STYLE_ACCENT, STYLE_BOLD, STYLE_DIM, STYLE_ERROR,
    STYLE_RESET, STYLE_SUCCESS, STYLE_WARNING, SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS,
)
from .credentials import find_api_key, keyring_available, save_keyring_key
from .denoise import ENGINE_DEEPFILTERNET, ENGINE_RNNOISE, ENGINE_SPECTRAL
from .gemini_config import gemini_label
from .models import EnhancerContext
from .system import find_local_media_files, is_supported_file
from .ui import display_summary_card, format_file_size


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
        ("2", f"AI Smart Cuts Only      - {gemini_label()} cuts 'um', 'uh', & dead silence"),
        ("3", f"AI Subtitles Only       - {gemini_label()} generates synchronized captions (.srt/.vtt)"),
        ("4", f"Both AI Cuts & Subtitles- Smart silence cuts + synchronized subtitle files"),
    ]
    choice = prompt_menu_choice(f"🤖 Step 7: AI Smart Cuts & Caption Generation ({gemini_label()})", options, default_key="1")

    use_cuts = choice in ("2", "4")
    use_subtitles = choice in ("3", "4")
    subtitle_formats = ["srt"]

    if use_subtitles:
        subtitle_formats = prompt_for_subtitle_formats()

    return use_cuts, use_subtitles, subtitle_formats


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Ask a yes/no question; Enter accepts the default."""
    hint = "Y/n" if default else "y/N"
    while True:
        response = input(f"\n  {STYLE_BOLD}{question} [{hint}]: {STYLE_RESET}").strip().lower()
        if not response:
            return default
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print(f"    {STYLE_ERROR}[!] Please enter 'y' or 'n'.{STYLE_RESET}")


def ensure_gemini_api_key() -> bool:
    """Find the Gemini API key (environment/.env, then keyring) or prompt for one."""
    api_key, source = find_api_key()
    if api_key:
        print(f"    {STYLE_DIM}Using Gemini API key from {source}.{STYLE_RESET}")
        return True

    print(f"\n  {STYLE_WARNING}[!] No Gemini API key found (environment, .env or system keyring).{STYLE_RESET}")
    print(f"      {gemini_label()} requires an API key for smart cutting & subtitle generation.")
    api_key_input = getpass.getpass("  > Paste your Gemini API Key (hidden; press Enter to skip AI): ").strip()
    if api_key_input:
        os.environ["GEMINI_API_KEY"] = api_key_input
        print(f"    {STYLE_SUCCESS}[OK] API Key configured for this session.{STYLE_RESET}")
        if keyring_available() and prompt_yes_no("Save it to your system keyring for next time?", default=False):
            if save_keyring_key(api_key_input):
                print(f"    {STYLE_SUCCESS}[OK] Saved to system keyring.{STYLE_RESET}")
            else:
                print(f"    {STYLE_WARNING}[!] Could not access a system keyring; the key was not saved.{STYLE_RESET}")
        return True

    print(f"    {STYLE_DIM}Skipping AI features - proceeding with local DSP only.{STYLE_RESET}")
    return False


def prompt_for_denoise_engine() -> str:
    """Ask which noise-reduction engine to use."""
    options = [
        ("1", "Spectral Gating  - Built in, fast, good for steady hiss & hum (default)"),
        ("2", "RNNoise (neural) - Better on speech with changing noise; needs a small model file"),
        ("3", "DeepFilterNet    - Highest quality neural denoise; needs 'pip install deepfilternet' (PyTorch)"),
    ]
    choice = prompt_menu_choice("🧠 Noise Reduction Engine", options, default_key="1")
    return {"1": ENGINE_SPECTRAL, "2": ENGINE_RNNOISE, "3": ENGINE_DEEPFILTERNET}[choice]


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


def prompt_for_silence_removal() -> bool:
    """Ask whether to trim dead silence locally (free, no AI or API key needed)."""
    while True:
        response = input(
            f"\n  {STYLE_BOLD}Remove dead silence locally (no AI needed)? [y/N]: {STYLE_RESET}"
        ).strip().lower()
        if response in ("", "n", "no"):
            return False
        if response in ("y", "yes"):
            return True
        print(f"    {STYLE_ERROR}[!] Please enter 'y' or 'n'.{STYLE_RESET}")
