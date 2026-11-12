"""CLI argument parsing, configuration resolution and entry point."""

from __future__ import annotations

import argparse
import getpass
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from .constants import (
    APP_NAME, DEFAULT_MAX_WORKERS, MAX_LUFS_TARGET,
    MAX_PLAYBACK_SPEED, MIN_LUFS_TARGET, MIN_PLAYBACK_SPEED, STYLE_ERROR,
    STYLE_BOLD, STYLE_RESET, STYLE_SUCCESS, STYLE_WARNING, SUPPORTED_AUDIO_EXTENSIONS, SUPPORTED_VIDEO_EXTENSIONS,
    DEFAULT_SILENCE_THRESHOLD_DB, VERSION,
)
from .batch import (
    BatchResult, collect_input_files, derive_file_context, find_output_collisions,
    format_batch_summary,
)
from .credentials import delete_keyring_key, keyring_available, save_keyring_key
from .denoise import (
    DEFAULT_DENOISE_ENGINE, DENOISE_ENGINES, ENGINE_RNNOISE, DenoiseEngineError,
    download_rnnoise_model, engine_unavailable_reason, ffmpeg_has_arnndn,
    resolve_rnnoise_model,
)
from .env import load_dotenv
from .gemini_config import set_active_model
from .models import EnhancerContext
from .pipeline import run_pipeline
from .prompts import (
    ensure_gemini_api_key, prompt_for_ai_and_subtitles, prompt_for_audio_format,
    prompt_for_denoise_engine, prompt_for_denoise_strength, prompt_for_job_confirmation,
    prompt_for_loudness_normalization, prompt_for_output_mode,
    prompt_for_playback_speed, prompt_for_silence_removal, prompt_for_source_file,
    prompt_yes_no,
)
from .system import classify_input_file, verify_ffmpeg_installed
from .ui import configure_terminal_environment, display_batch_files, display_header_banner


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


def parse_silence_threshold_argument(raw_value: str) -> float:
    """Validate the silence threshold in dB (negative, between -90 and -10)."""
    try:
        val = float(raw_value.lower().rstrip("db ").strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid silence threshold: '{raw_value}'") from exc
    if val > 0:
        val = -val
    if not (-90.0 <= val <= -10.0):
        raise argparse.ArgumentTypeError(f"Silence threshold must be between -90 and -10 dB (got {val}).")
    return val


def parse_output_target(raw_value: str) -> tuple[Optional[Path], Optional[Path]]:
    """Interpret --output as either a directory or an explicit file path.

    Returns ``(output_dir, output_file)`` with exactly one set. A value is treated
    as a directory if it ends with a path separator, is an existing directory, or
    has no file extension.
    """
    path = Path(raw_value).expanduser()
    if raw_value.endswith(("/", "\\")) or path.is_dir() or not path.suffix:
        return path.resolve(), None
    return None, path.resolve()


def determine_output_mode(extension: str, is_video: bool) -> bool:
    """Return True if an explicit output extension means 'extract audio only'.

    Raises ValueError if the extension is not valid for the given input type.
    """
    ext = extension.lower()
    if ext in SUPPORTED_AUDIO_EXTENSIONS:
        return is_video
    if is_video and ext in SUPPORTED_VIDEO_EXTENSIONS:
        return False
    allowed = SUPPORTED_AUDIO_EXTENSIONS | (SUPPORTED_VIDEO_EXTENSIONS if is_video else set())
    raise ValueError(f"Unsupported output extension '{ext}'. Supported: {', '.join(sorted(allowed))}")


def build_argument_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser with optional interactive flags."""
    parser = argparse.ArgumentParser(
        prog="kavara-enhancer",
        description=f"{APP_NAME} v{VERSION} — Enhance audio & video files interactively or with flags.",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        metavar="FILE",
        help="Audio/video files, folders or glob patterns (e.g. *.mp4). More than one file runs as a batch.",
    )
    parser.add_argument(
        "--file", "-f",
        nargs="+",
        metavar="FILE",
        help="Source audio/video file(s), folder(s) or glob pattern(s); several files run as a batch.",
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
        help="Enable Gemini to detect and cut filler words, repeated phrases & silences.",
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
        help="Generate synchronized subtitle/caption files using Gemini.",
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
        "--output", "-o",
        type=str,
        help="Output file path (e.g. out/clean.mp3) or directory (e.g. out/). "
             "Default: <name>_enhanced.<ext> in the current directory.",
    )
    parser.add_argument(
        "--cut-silence",
        action="store_true",
        default=False,
        help="Trim dead silence locally with FFmpeg (free, no AI or API key needed). Implied by --use-ai.",
    )
    parser.add_argument(
        "--silence-threshold",
        type=parse_silence_threshold_argument,
        default=DEFAULT_SILENCE_THRESHOLD_DB,
        metavar="DB",
        help=f"Level in dB below which audio counts as silence (default: {DEFAULT_SILENCE_THRESHOLD_DB:g}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview the plan and detected cuts without writing any output files.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="MODEL_ID",
        help="Gemini model id to use (e.g. gemini-2.5-flash). Default: $GEMINI_MODEL or the built-in default.",
    )
    parser.add_argument(
        "--denoise-engine",
        choices=DENOISE_ENGINES,
        default=None,
        help="Noise reduction engine: spectral (default), rnnoise (FFmpeg arnndn) or deepfilternet (needs PyTorch).",
    )
    parser.add_argument(
        "--rnnoise-model",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to an RNNoise .rnnn model (implies --denoise-engine rnnoise). Default: $KAVARA_RNNOISE_MODEL or the downloaded model.",
    )
    parser.add_argument(
        "--download-rnnoise-model",
        action="store_true",
        default=False,
        help="Download and verify the RNNoise model (about 300 KB), then exit.",
    )
    parser.add_argument(
        "--save-api-key",
        action="store_true",
        default=False,
        help="Prompt for your Gemini API key and store it in the system keyring, then exit.",
    )
    parser.add_argument(
        "--delete-api-key",
        action="store_true",
        default=False,
        help="Remove the Gemini API key from the system keyring, then exit.",
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


def prepare_denoise_engine(engine: str, model_arg: Optional[str], interactive: bool) -> Optional[Path]:
    """Validate the chosen denoise engine up front; returns the RNNoise model path if relevant.

    Exits with a clear message instead of failing halfway through a long job.
    """
    model: Optional[Path] = None
    try:
        if engine == ENGINE_RNNOISE:
            model = resolve_rnnoise_model(Path(model_arg).expanduser() if model_arg else None)
            if (
                model is None and interactive and ffmpeg_has_arnndn()
                and prompt_yes_no("No RNNoise model found. Download it now (about 300 KB)?", default=True)
            ):
                model = download_rnnoise_model()
                print(f"    {STYLE_SUCCESS}[OK] Model saved to {model}{STYLE_RESET}")
    except DenoiseEngineError as exc:
        print(f"\n{STYLE_ERROR}[ERROR] {exc}{STYLE_RESET}")
        sys.exit(1)

    reason = engine_unavailable_reason(engine, model)
    if reason:
        print(f"\n{STYLE_ERROR}[ERROR] {reason}{STYLE_RESET}")
        sys.exit(1)
    return model


def resolve_execution_contexts(args: argparse.Namespace) -> Optional[list[EnhancerContext]]:
    """Resolve pipeline settings (flags + interactive prompts) into one job per input file."""
    set_active_model(args.model)

    patterns = [*(args.inputs or []), *(args.file or [])]
    is_interactive_mode = args.interactive or not patterns

    # Step 1: Input file(s)
    if patterns:
        input_files, problems = collect_input_files(patterns)
        for problem in problems:
            print(f"\n{STYLE_ERROR}[ERROR] {problem}{STYLE_RESET}")
        if problems or not input_files:
            sys.exit(1)
    else:
        input_files = [prompt_for_source_file()]

    input_path = input_files[0]
    is_batch = len(input_files) > 1
    is_video = classify_input_file(input_path)

    # Explicit --output target (directory or file)
    output_dir: Optional[Path] = None
    output_file: Optional[Path] = None
    forced_ext: Optional[str] = None
    if args.output:
        output_dir, output_file = parse_output_target(args.output)
        if output_file is not None:
            forced_ext = output_file.suffix.lower()
            try:
                forced_extract = determine_output_mode(forced_ext, is_video)
            except ValueError as exc:
                print(f"\n{STYLE_ERROR}[ERROR] {exc}{STYLE_RESET}")
                sys.exit(1)
            if args.extract_audio and not forced_extract:
                print(f"\n{STYLE_ERROR}[ERROR] --extract-audio conflicts with video output '{forced_ext}'.{STYLE_RESET}")
                sys.exit(1)

    if is_batch and output_file is not None:
        print(f"\n{STYLE_ERROR}[ERROR] --output must be a folder when processing multiple files.{STYLE_RESET}")
        sys.exit(1)

    # Step 2: Output Mode (Video vs Audio extraction)
    if forced_ext:
        extract_audio_mode = forced_extract
    elif is_video:
        if args.extract_audio or args.format:
            extract_audio_mode = True
        elif is_interactive_mode:
            extract_audio_mode = prompt_for_output_mode(is_video)
        else:
            extract_audio_mode = False
    else:
        extract_audio_mode = False

    # Step 3: Target Output Format
    if forced_ext:
        target_format = forced_ext
    elif is_video and not extract_audio_mode:
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

    # Step 5b: Noise reduction engine
    denoise_engine = DEFAULT_DENOISE_ENGINE
    rnnoise_model: Optional[Path] = None
    if denoise_strength > 0.0:
        if args.denoise_engine:
            denoise_engine = args.denoise_engine
        elif args.rnnoise_model:
            denoise_engine = ENGINE_RNNOISE
        elif is_interactive_mode:
            denoise_engine = prompt_for_denoise_engine()
        rnnoise_model = prepare_denoise_engine(denoise_engine, args.rnnoise_model, is_interactive_mode)

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

    # Local silence removal (implied by AI cuts, which only analyse filler words)
    if args.cut_silence or use_ai_cuts:
        cut_silence = True
    elif is_interactive_mode and not args.dry_run:
        cut_silence = prompt_for_silence_removal()
    else:
        cut_silence = False

    max_workers = max(1, args.workers) if hasattr(args, "workers") and args.workers else DEFAULT_MAX_WORKERS

    context = EnhancerContext(
        input_path=input_path,
        speed=playback_speed,
        use_ai=use_ai_cuts,
        generate_subtitles=use_subtitles,
        subtitle_formats=subtitle_formats,
        max_workers=max_workers,
        denoise_strength=denoise_strength,
        denoise_engine=denoise_engine,
        rnnoise_model=rnnoise_model,
        normalize_lufs=normalize_lufs,
        is_video=is_video,
        extract_audio=extract_audio_mode,
        output_format=target_format,
        cut_silence=cut_silence,
        silence_threshold_db=args.silence_threshold,
        dry_run=args.dry_run,
        output_dir=output_dir,
        output_file=output_file,
    )

    contexts = [context]
    if is_batch:
        # Per-file details (video vs audio, output extension, default loudness) are
        # recomputed; everything chosen once above applies to every file.
        extract_pref = extract_audio_mode if is_video else bool(args.extract_audio or args.format)
        if args.format:
            audio_format: Optional[str] = target_format
        elif is_interactive_mode and (extract_audio_mode or not is_video):
            audio_format = target_format
        else:
            audio_format = None
        normalize_is_default = not (args.no_normalize or args.normalize_lufs is not None or is_interactive_mode)

        contexts.extend(
            derive_file_context(
                context, path,
                extract_audio_pref=extract_pref,
                audio_format=audio_format,
                normalize_is_default=normalize_is_default,
            )
            for path in input_files[1:]
        )

        collisions = find_output_collisions(contexts)
        if collisions:
            for output, sources in collisions.items():
                names = ", ".join(str(source) for source in sources)
                print(f"\n{STYLE_ERROR}[ERROR] These inputs would all write {output}: {names}{STYLE_RESET}")
            print("        Process them in separate runs or give each its own --output folder.")
            sys.exit(1)

    if is_interactive_mode:
        if is_batch:
            display_batch_files(input_files)
        confirmed = prompt_for_job_confirmation(context)
        if not confirmed:
            print(f"\n  {STYLE_WARNING}[*] Enhancement aborted by user.{STYLE_RESET}\n")
            return None

    return contexts


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def run_batch(contexts: list[EnhancerContext]) -> list[BatchResult]:
    """Run each job in turn; one failing file does not stop the rest."""
    results: list[BatchResult] = []
    total = len(contexts)

    for index, ctx in enumerate(contexts, start=1):
        if total > 1:
            print(f"\n{STYLE_BOLD}━━━ File {index}/{total}: {ctx.input_path.name} ━━━{STYLE_RESET}")
        started = time.time()
        try:
            with tempfile.TemporaryDirectory(prefix="kavara_") as temporary_workspace:
                ctx.temp_dir = temporary_workspace
                run_pipeline(ctx)
            results.append(BatchResult(ctx.input_path, ctx.output_path, True, time.time() - started))
        except KeyboardInterrupt:
            raise
        except Exception as error:
            print(f"\n{STYLE_ERROR}[ERROR] {error}{STYLE_RESET}\n")
            results.append(BatchResult(ctx.input_path, ctx.output_path, False, time.time() - started, str(error)))

    return results


def run_standalone_actions(args: argparse.Namespace) -> bool:
    """Handle flags that do a single job and exit. Returns True if one was handled."""
    if args.download_rnnoise_model:
        try:
            path = download_rnnoise_model()
        except DenoiseEngineError as exc:
            print(f"\n{STYLE_ERROR}[ERROR] {exc}{STYLE_RESET}\n")
            sys.exit(1)
        print(f"\n  {STYLE_SUCCESS}[OK] RNNoise model saved to {path}{STYLE_RESET}\n")
        return True

    if args.save_api_key:
        if not keyring_available():
            print(f"\n{STYLE_ERROR}[ERROR] The 'keyring' package is not installed. "
                  f"Run: pip install \"kavara-audio-enhancer[keyring]\"{STYLE_RESET}\n")
            sys.exit(1)
        api_key = getpass.getpass("  > Paste your Gemini API Key (hidden): ").strip()
        if not api_key:
            print(f"\n{STYLE_ERROR}[ERROR] No key entered; nothing saved.{STYLE_RESET}\n")
            sys.exit(1)
        if not save_keyring_key(api_key):
            print(f"\n{STYLE_ERROR}[ERROR] Could not access a system keyring backend.{STYLE_RESET}\n")
            sys.exit(1)
        print(f"\n  {STYLE_SUCCESS}[OK] API key saved to the system keyring.{STYLE_RESET}\n")
        return True

    if args.delete_api_key:
        if delete_keyring_key():
            print(f"\n  {STYLE_SUCCESS}[OK] API key removed from the system keyring.{STYLE_RESET}\n")
        else:
            print(f"\n  {STYLE_WARNING}[!] No stored API key was found (or no keyring is available).{STYLE_RESET}\n")
        return True

    return False


def main() -> None:
    """Main application entry point."""
    load_dotenv()
    configure_terminal_environment()
    display_header_banner()

    parser = build_argument_parser()
    args = parser.parse_intermixed_args()

    if run_standalone_actions(args):
        return

    verify_ffmpeg_installed()

    try:
        contexts = resolve_execution_contexts(args)
        if contexts is None:
            return
        results = run_batch(contexts)
    except KeyboardInterrupt:
        print(f"\n\n  {STYLE_WARNING}[x] Process cancelled by user. Exiting...{STYLE_RESET}\n")
        sys.exit(0)
    except Exception as error:
        print(f"\n{STYLE_ERROR}[ERROR] {error}{STYLE_RESET}\n")
        sys.exit(1)

    if len(results) > 1:
        print(f"\n{STYLE_BOLD}Batch summary{STYLE_RESET}")
        for line in format_batch_summary(results).splitlines():
            print(f"  {line}")
        print()

    if any(not result.success for result in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
