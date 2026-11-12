"""Pipeline orchestrator."""

from __future__ import annotations

import os
import time

from .ai import build_subtitles_from_words, create_analysis_payload, transcribe_words
from .assembly import encode_audio_output, merge_audio_video, merge_cut_video_and_audio
from .constants import (
    MAX_CUT_FRACTION, STYLE_BOLD, STYLE_DIM, STYLE_RESET,
    STYLE_SUCCESS, STYLE_WARNING,
)
from .denoise import ENGINE_LABELS, denoise_audio
from .disfluency import find_disfluency_cuts
from .cutting import apply_cuts_audio_only, sanitize_cuts, total_cut_duration
from .dsp import (
    change_speed_preserve_pitch, extract_audio, normalize_audio_loudness,
)
from .gemini_config import gemini_label
from .models import CutSegment, EnhancerContext, TimedWord
from .silence import detect_silences
from .subtitles import save_subtitle_files
from .system import get_audio_duration
from .timeline import remap_words
from .ui import display_completion_banner, format_cut_report, log_step


def ensure_transcript(ctx: EnhancerContext, raw_wav: str) -> list[TimedWord]:
    """Transcribe the original audio once; cuts and subtitles share the result.

    Raises the original error again on later calls instead of paying for a retry.
    """
    if ctx.transcript_error is not None:
        raise RuntimeError(ctx.transcript_error)
    if ctx.transcript_words is None:
        try:
            payload = create_analysis_payload(raw_wav, ctx.temp_dir, "transcript_payload")
            ctx.transcript_words = transcribe_words(payload, ctx.temp_dir, max_workers=ctx.max_workers)
        except Exception as exc:
            ctx.transcript_error = str(exc)
            raise
    return ctx.transcript_words


def detect_cuts(ctx: EnhancerContext, raw_wav: str, duration: float) -> list[CutSegment]:
    """Collect, validate and merge cuts from local silence detection and/or Gemini.

    When AI is enabled, silence is found locally (free and precise) and Gemini is
    only asked for filler words. AI failures degrade gracefully to local cuts.
    """
    cuts: list[CutSegment] = []

    if ctx.cut_silence or ctx.use_ai:
        silences = detect_silences(raw_wav, duration, threshold_db=ctx.silence_threshold_db)
        print(f"    {STYLE_SUCCESS}[OK] Local detection found {len(silences)} silent gap(s) to trim.{STYLE_RESET}")
        cuts.extend(silences)

    if ctx.use_ai:
        try:
            fillers = find_disfluency_cuts(ensure_transcript(ctx, raw_wav))
            print(f"    {STYLE_SUCCESS}[OK] {gemini_label()} transcript flagged {len(fillers)} filler/repeat segment(s).{STYLE_RESET}")
            cuts.extend(fillers)
        except Exception as ai_err:
            print(f"    {STYLE_WARNING}[!] AI filler analysis failed ({ai_err}); continuing with local cuts only.{STYLE_RESET}")

    cuts = sanitize_cuts(cuts, duration)

    if cuts and duration > 0 and total_cut_duration(cuts) / duration > MAX_CUT_FRACTION:
        print(
            f"    {STYLE_WARNING}[!] Planned cuts would remove more than {int(MAX_CUT_FRACTION * 100)}% "
            f"of the file; ignoring them as unreliable.{STYLE_RESET}"
        )
        return []
    return cuts


def run_dry_run(ctx: EnhancerContext) -> None:
    """Preview what would happen: detect and list cuts, but write no output."""
    print(f"\n  {STYLE_BOLD}DRY RUN{STYLE_RESET} {STYLE_DIM}- nothing will be written.{STYLE_RESET}")
    if ctx.output_path.exists():
        print(f"    {STYLE_WARNING}[!] {ctx.output_path} already exists and would be overwritten.{STYLE_RESET}")

    if not (ctx.cut_silence or ctx.use_ai):
        print(f"    {STYLE_DIM}No cut detection enabled; the configuration above is the full plan.{STYLE_RESET}\n")
        return

    raw_wav = os.path.join(ctx.temp_dir, "raw_audio.wav")
    log_step(1, 2, "Extracting audio for analysis...")
    extract_audio(ctx.input_path, raw_wav)
    duration = get_audio_duration(raw_wav)

    log_step(2, 2, "Detecting cuts...")
    cuts = detect_cuts(ctx, raw_wav, duration)

    print(f"\n  {STYLE_BOLD}Planned cuts{STYLE_RESET}")
    for line in format_cut_report(cuts, duration, ctx.speed).splitlines():
        print(f"    {line}")
    print(f"\n  {STYLE_DIM}Dry run complete. Re-run without --dry-run to apply.{STYLE_RESET}\n")


def run_pipeline(ctx: EnhancerContext) -> None:
    """Execute the full enhancement pipeline."""
    if ctx.dry_run:
        run_dry_run(ctx)
        return

    start_time = time.time()
    ctx.output_path.parent.mkdir(parents=True, exist_ok=True)

    total_steps = (
        1                                               # Step 1: Extract/Decode audio
        + (1 if (ctx.use_ai or ctx.cut_silence) else 0)  # Cut detection
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

    # --- Step: Cut Detection (local silence + AI fillers) ---
    if ctx.use_ai or ctx.cut_silence:
        current_step += 1
        label = f"local silence + {gemini_label()} fillers" if ctx.use_ai else "local silence detection"
        log_step(current_step, total_steps, f"Detecting cuts ({label})...")

        duration = get_audio_duration(raw_wav)
        ctx.cut_segments = detect_cuts(ctx, raw_wav, duration)

        if ctx.cut_segments:
            removed = total_cut_duration(ctx.cut_segments)
            print(f"    {STYLE_SUCCESS}[OK] Removing {len(ctx.cut_segments)} segment(s), {removed:.1f}s total.{STYLE_RESET}")
            apply_cuts_audio_only(raw_wav, cut_wav, ctx.cut_segments, duration)
            working_wav = cut_wav
        else:
            print(f"    {STYLE_SUCCESS}[OK] Nothing to cut.{STYLE_RESET}")

    # --- Step: Noise Reduction ---
    if ctx.denoise_strength > 0.0:
        current_step += 1
        percentage_label = int(ctx.denoise_strength * 100)
        log_step(current_step, total_steps, f"Reducing background noise ({percentage_label}% {ENGINE_LABELS.get(ctx.denoise_engine, ctx.denoise_engine)})...")
        denoise_audio(working_wav, denoised_wav, ctx.denoise_strength, ctx.denoise_engine, ctx.rnnoise_model)
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
        reuse = ctx.transcript_words is not None
        log_step(
            current_step, total_steps,
            "Building subtitles from the existing transcript..." if reuse
            else f"Transcribing for subtitles with {gemini_label()}...",
        )
        try:
            # One transcript of the original audio, re-timed to the edited output.
            words = remap_words(ensure_transcript(ctx, raw_wav), ctx.cut_segments, ctx.speed)
            ctx.subtitle_entries = build_subtitles_from_words(words)
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
