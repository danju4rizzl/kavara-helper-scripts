"""
Kavara Audio Enhancer -- CLI audio/video enhancement tool.

Pipeline: Ingest -> Extract -> [AI Cut] -> Denoise -> Time-Stretch -> Output
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
import noisereduce as nr
import soundfile as sf

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME = "Kavara Audio Enhancer"
VERSION = "1.0.0"

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts"}
VALID_SPEEDS = {1.0, 1.5, 2.0}

GEMINI_SYSTEM_INSTRUCTION = (
    "You are an expert audio editing assistant. "
    "Analyze this audio track and identify all filler words "
    "(e.g., 'um', 'uh', 'ah', 'humm', 'like') and periods of absolute silence "
    "lasting longer than 0.5 seconds. "
    "Return a strict JSON object mapping the exact start_time and end_time "
    "in seconds for every segment that should be cut."
)

SAMPLE_RATE = 44100  # Hz -- standard CD-quality sample rate


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class CutSegment:
    """A time range (in seconds) that should be removed from the audio."""

    start_time: float
    end_time: float


@dataclass
class EnhancerContext:
    """Holds all state needed throughout the enhancement pipeline."""

    input_path: Path
    speed: float
    use_ai: bool
    is_video: bool = False
    extract_audio: bool = False
    output_format: Optional[str] = None
    temp_dir: str = ""
    cut_segments: list[CutSegment] = field(default_factory=list)

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
# Utilities
# ---------------------------------------------------------------------------

def _configure_utf8_output() -> None:
    """Attempt to reconfigure stdout/stderr to UTF-8 on Windows."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # Fallback: ASCII-only output will still work


def log_step(step: int, total: int, message: str) -> None:
    """Print a formatted progress step to the console."""
    print(f"\n  [{step}/{total}] {message}")


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
            "\n[ERROR] FFmpeg is not installed or not found on your PATH.\n"
            "        Install it from https://ffmpeg.org/download.html\n"
            "        and ensure the 'ffmpeg' binary is accessible from your terminal."
        )
        sys.exit(1)


def classify_input_file(file_path: Path) -> bool:
    """Return True if the file is a video, False if audio. Exit on unsupported."""
    ext = file_path.suffix.lower()
    if ext in SUPPORTED_VIDEO_EXTENSIONS:
        return True
    if ext in SUPPORTED_AUDIO_EXTENSIONS:
        return False
    print(f"\n[ERROR] Unsupported file format: '{ext}'")
    print(f"        Supported audio: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}")
    print(f"        Supported video: {', '.join(sorted(SUPPORTED_VIDEO_EXTENSIONS))}")
    sys.exit(1)


def get_audio_duration(file_path: str) -> float:
    """Probe the duration of an audio file in seconds via FFmpeg."""
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


def reduce_noise(input_wav: str, output_wav: str) -> None:
    """Apply spectral-gated noise reduction to a WAV file."""
    audio_data, sample_rate = sf.read(input_wav)
    reduced = nr.reduce_noise(y=audio_data, sr=sample_rate, prop_decrease=0.8)
    sf.write(output_wav, reduced, sample_rate)


def change_speed_preserve_pitch(input_wav: str, output_wav: str, speed: float) -> None:
    """Time-stretch audio by the given factor without altering pitch.

    Uses librosa's phase-vocoder based time_stretch which preserves
    pitch by operating in the STFT domain.
    """
    if speed == 1.0:
        shutil.copy2(input_wav, output_wav)
        return

    audio_data, sample_rate = librosa.load(input_wav, sr=None, mono=True)
    stretched = librosa.effects.time_stretch(audio_data, rate=speed)
    sf.write(output_wav, stretched, sample_rate)


# ---------------------------------------------------------------------------
# Gemini AI Engine
# ---------------------------------------------------------------------------

def create_analysis_payload(input_wav: str, temp_dir: str) -> str:
    """Compress the WAV down to a small 64 kbps MP3 for fast upload to Gemini."""
    mp3_path = os.path.join(temp_dir, "analysis_payload.mp3")
    run_ffmpeg(
        ["-i", input_wav, "-b:a", "64k", "-ar", "16000", "-ac", "1", mp3_path],
        description="analysis payload compression",
    )
    return mp3_path


def _build_gemini_response_schema():
    """Return the Pydantic-based schema class for Gemini structured output."""
    from pydantic import BaseModel

    class Segment(BaseModel):
        start_time: float
        end_time: float
        label: str  # e.g. "filler_word" or "silence"

    class AnalysisResult(BaseModel):
        segments_to_cut: list[Segment]

    return AnalysisResult


def analyze_audio_with_gemini(mp3_path: str) -> list[CutSegment]:
    """Upload audio to Gemini 2.5 Flash and retrieve cut timestamps."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY environment variable is not set.\n"
            "Set it with:  export GEMINI_API_KEY='your_key_here'"
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    print("    >> Uploading audio to Gemini...")
    uploaded_file = client.files.upload(file=mp3_path)

    AnalysisResult = _build_gemini_response_schema()

    print("    >> Analyzing audio with Gemini 2.5 Flash...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_uri(
                        file_uri=uploaded_file.uri,
                        mime_type=uploaded_file.mime_type,
                    ),
                    types.Part.from_text(
                        "Analyze this audio. Identify all filler words and "
                        "silence periods longer than 0.5 seconds. Return the "
                        "timestamps of segments to cut."
                    ),
                ],
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=GEMINI_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=AnalysisResult,
        ),
    )

    result = AnalysisResult.model_validate_json(response.text)

    # Clean up uploaded file
    try:
        client.files.delete(name=uploaded_file.name)
    except Exception:
        pass  # Non-critical — file will auto-expire

    return [
        CutSegment(start_time=seg.start_time, end_time=seg.end_time)
        for seg in result.segments_to_cut
    ]


# ---------------------------------------------------------------------------
# Smart Cutting Engine
# ---------------------------------------------------------------------------

def _invert_segments(cuts: list[CutSegment], total_duration: float) -> list[tuple[float, float]]:
    """Convert a list of segments-to-remove into a list of segments-to-keep.

    Sorts cuts, merges overlaps, then returns the complement intervals
    within [0, total_duration].
    """
    if not cuts:
        return [(0.0, total_duration)]

    sorted_cuts = sorted(cuts, key=lambda s: s.start_time)

    merged: list[tuple[float, float]] = []
    current_start = sorted_cuts[0].start_time
    current_end = sorted_cuts[0].end_time
    for seg in sorted_cuts[1:]:
        if seg.start_time <= current_end:
            current_end = max(current_end, seg.end_time)
        else:
            merged.append((current_start, current_end))
            current_start = seg.start_time
            current_end = seg.end_time
    merged.append((current_start, current_end))

    keeps: list[tuple[float, float]] = []
    prev_end = 0.0
    for cut_start, cut_end in merged:
        if prev_end < cut_start:
            keeps.append((prev_end, cut_start))
        prev_end = cut_end
    if prev_end < total_duration:
        keeps.append((prev_end, total_duration))

    return keeps


def generate_cut_filter(
    cuts: list[CutSegment],
    total_duration: float,
    has_video: bool,
) -> str:
    """Build an FFmpeg complex filtergraph that trims out the cut segments.

    Produces a series of trim/atrim filters concatenated together.
    Returns the full -filter_complex string.
    """
    keeps = _invert_segments(cuts, total_duration)
    if not keeps:
        raise ValueError("AI requested cutting the entire file — nothing to keep.")

    parts: list[str] = []
    video_labels: list[str] = []
    audio_labels: list[str] = []

    for i, (start, end) in enumerate(keeps):
        if has_video:
            parts.append(
                f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}];"
            )
            video_labels.append(f"[v{i}]")

        parts.append(
            f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}];"
        )
        audio_labels.append(f"[a{i}]")

    segment_count = len(keeps)

    if has_video:
        concat_input = "".join(
            f"{video_labels[i]}{audio_labels[i]}" for i in range(segment_count)
        )
        parts.append(
            f"{concat_input}concat=n={segment_count}:v=1:a=1[outv][outa]"
        )
    else:
        concat_input = "".join(audio_labels)
        parts.append(
            f"{concat_input}concat=n={segment_count}:v=0:a=1[outa]"
        )

    return "".join(parts)


def apply_cuts_audio_only(
    input_wav: str,
    output_wav: str,
    cuts: list[CutSegment],
    total_duration: float,
) -> None:
    """Remove the cut segments from an audio-only file."""
    filtergraph = generate_cut_filter(cuts, total_duration, has_video=False)
    run_ffmpeg(
        ["-i", input_wav, "-filter_complex", filtergraph,
         "-map", "[outa]", "-acodec", "pcm_s16le", output_wav],
        description="AI audio cuts",
    )


def apply_cuts_video(
    input_video: str,
    input_audio: str,
    output_path: str,
    cuts: list[CutSegment],
    total_duration: float,
) -> None:
    """Remove the cut segments from both video and audio tracks simultaneously."""
    filtergraph = generate_cut_filter(cuts, total_duration, has_video=True)
    run_ffmpeg(
        ["-i", input_video, "-i", input_audio,
         "-filter_complex", filtergraph,
         "-map", "[outv]", "-map", "[outa]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-c:a", "aac", "-b:a", "192k",
         output_path],
        description="AI video+audio cuts",
    )


# ---------------------------------------------------------------------------
# Final Assembly
# ---------------------------------------------------------------------------

def encode_audio_output(input_wav: str, output_path: Path) -> None:
    """Encode the processed WAV to the target output format."""
    ext = output_path.suffix.lower()
    codec_args: list[str] = []

    if ext == ".mp3":
        codec_args = ["-c:a", "libmp3lame", "-b:a", "192k"]
    elif ext == ".aac" or ext == ".m4a":
        codec_args = ["-c:a", "aac", "-b:a", "192k"]
    elif ext == ".flac":
        codec_args = ["-c:a", "flac"]
    elif ext == ".ogg":
        codec_args = ["-c:a", "libvorbis", "-b:a", "192k"]
    elif ext == ".opus":
        codec_args = ["-c:a", "libopus", "-b:a", "128k"]
    elif ext == ".wav":
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
    """Remux enhanced audio back into the original video container.

    When speed != 1.0, the video track is sped up via setpts to stay in sync.
    """
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_argument_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="kavara-enhancer",
        description=f"{APP_NAME} v{VERSION} — Enhance audio & video files",
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Path to the source audio or video file.",
    )
    parser.add_argument(
        "--speed", "-s",
        type=float,
        choices=sorted(VALID_SPEEDS),
        help="Playback speed multiplier (1.0, 1.5, or 2.0). Default: prompted.",
    )
    parser.add_argument(
        "--use-ai",
        action="store_true",
        default=False,
        help="Enable Gemini AI to detect and cut filler words & silences.",
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
        "--version", "-v",
        action="version",
        version=f"{APP_NAME} v{VERSION}",
    )
    return parser


def prompt_for_file() -> str:
    """Interactively ask the user for the source file path."""
    while True:
        path = input("\n  Enter the path to your audio/video file: ").strip().strip('"')
        if Path(path).is_file():
            return path
        print(f"    [!] File not found: '{path}'. Please try again.")


def prompt_for_speed() -> float:
    """Interactively ask the user for the desired speed."""
    print("\n  Select playback speed:")
    print("     [1] Normal  (1.0x)")
    print("     [2] Fast    (1.5x)")
    print("     [3] Fastest (2.0x)")
    speed_map = {"1": 1.0, "2": 1.5, "3": 2.0}
    while True:
        choice = input("  > Your choice (1/2/3): ").strip()
        if choice in speed_map:
            return speed_map[choice]
        print("    [!] Invalid choice. Enter 1, 2, or 3.")


def prompt_for_format(default_ext: str) -> str:
    """Interactively ask the user for the output audio format."""
    print("\n  Select output format:")
    print("     [1] MP3  (.mp3)")
    print("     [2] WAV  (.wav)")
    print("     [3] AAC  (.aac)")
    print("     [4] FLAC (.flac)")
    print(f"     [5] Default ({default_ext})")

    if not default_ext.startswith("."):
        default_ext = f".{default_ext}"

    format_map = {"1": ".mp3", "2": ".wav", "3": ".aac", "4": ".flac", "5": default_ext}
    while True:
        choice = input("  > Your choice (1/2/3/4/5): ").strip()
        if choice in format_map:
            return format_map[choice]
        print("    [!] Invalid choice. Enter 1, 2, 3, 4, or 5.")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(ctx: EnhancerContext) -> None:
    """Execute the full enhancement pipeline."""
    total_steps = 4 + (1 if ctx.use_ai else 0)
    current_step = 0

    raw_wav = os.path.join(ctx.temp_dir, "raw_audio.wav")
    cut_wav = os.path.join(ctx.temp_dir, "cut_audio.wav")
    denoised_wav = os.path.join(ctx.temp_dir, "denoised_audio.wav")
    final_wav = os.path.join(ctx.temp_dir, "final_audio.wav")

    # --- Step 1: Extract / Load Audio ---
    current_step += 1
    if ctx.is_video:
        log_step(current_step, total_steps, "Extracting audio from video...")
        extract_audio(ctx.input_path, raw_wav)
    else:
        log_step(current_step, total_steps, "Loading audio file...")
        extract_audio(ctx.input_path, raw_wav)
    print("    [OK] Audio ready.")

    working_wav = raw_wav

    # --- Step 2 (optional): AI Filler / Silence Detection ---
    if ctx.use_ai:
        current_step += 1
        log_step(current_step, total_steps, "Running AI analysis (Gemini 2.5 Flash)...")

        mp3_payload = create_analysis_payload(raw_wav, ctx.temp_dir)
        ctx.cut_segments = analyze_audio_with_gemini(mp3_payload)

        if ctx.cut_segments:
            print(f"    [OK] Found {len(ctx.cut_segments)} segment(s) to cut.")
            duration = get_audio_duration(raw_wav)
            apply_cuts_audio_only(raw_wav, cut_wav, ctx.cut_segments, duration)
            working_wav = cut_wav
        else:
            print("    [OK] No filler words or long silences detected.")

    # --- Step N: Noise Reduction ---
    current_step += 1
    log_step(current_step, total_steps, "Reducing background noise...")
    reduce_noise(working_wav, denoised_wav)
    print("    [OK] Noise reduction complete.")

    # --- Step N+1: Time-Stretching ---
    current_step += 1
    log_step(current_step, total_steps, f"Adjusting speed to {ctx.speed}x (pitch preserved)...")
    change_speed_preserve_pitch(denoised_wav, final_wav, ctx.speed)
    print("    [OK] Speed adjustment complete.")

    # --- Step N+2: Final Assembly ---
    current_step += 1
    log_step(current_step, total_steps, "Assembling final output...")

    if ctx.is_video and not ctx.extract_audio:
        # If AI made cuts AND speed != 1.0, we must handle the video track carefully.
        # The audio has already been cut. We need the video cut + sped up too.
        if ctx.cut_segments and ctx.speed != 1.0:
            # Cut the video first, then speed it up
            cut_video = os.path.join(ctx.temp_dir, "cut_video.mp4")
            duration = get_audio_duration(str(ctx.input_path))
            filtergraph = generate_cut_filter(ctx.cut_segments, duration, has_video=True)

            # Build the cut video (video-only) from original
            run_ffmpeg(
                ["-i", str(ctx.input_path),
                 "-filter_complex", filtergraph,
                 "-map", "[outv]", "-map", "[outa]",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-c:a", "pcm_s16le",
                 cut_video],
                description="cutting video track",
            )
            # Now remux the cut video with the enhanced audio at the new speed
            merge_audio_video(Path(cut_video), final_wav, ctx.output_path, ctx.speed)

        elif ctx.cut_segments:
            # Cuts but no speed change — cut both tracks simultaneously
            duration = get_audio_duration(str(ctx.input_path))

            # We already have the enhanced audio; we just need to cut + encode the video
            # and pair it with our final_wav
            cut_video_only = os.path.join(ctx.temp_dir, "cut_video_only.mp4")
            video_filter = generate_cut_filter(ctx.cut_segments, duration, has_video=True)
            run_ffmpeg(
                ["-i", str(ctx.input_path),
                 "-filter_complex", video_filter,
                 "-map", "[outv]",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-an", cut_video_only],
                description="cutting video track (no speed change)",
            )
            # Mux the cut video with enhanced audio
            run_ffmpeg(
                ["-i", cut_video_only, "-i", final_wav,
                 "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0",
                 "-c:a", "aac", "-b:a", "192k",
                 "-shortest", str(ctx.output_path)],
                description="final video assembly",
            )
        else:
            # No AI cuts — just remux with speed
            merge_audio_video(ctx.input_path, final_wav, ctx.output_path, ctx.speed)
    else:
        encode_audio_output(final_wav, ctx.output_path)

    print(f"\n  [DONE] Enhanced file saved to:\n         {ctx.output_path}\n")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point for the Kavara Audio Enhancer."""
    _configure_utf8_output()

    print(f"\n  +--------------------------------------+")
    print(f"  |       {APP_NAME} v{VERSION}       |")
    print(f"  +--------------------------------------+")

    verify_ffmpeg_installed()

    parser = build_argument_parser()
    args = parser.parse_args()

    file_path_str = args.file or prompt_for_file()
    input_path = Path(file_path_str).resolve()

    if not input_path.is_file():
        print(f"\n[ERROR] File not found: '{input_path}'")
        sys.exit(1)

    is_video = classify_input_file(input_path)

    extract_audio_flag = False
    output_format = None

    if is_video:
        if args.extract_audio or args.format:
            extract_audio_flag = True
        else:
            print("\n  Select output mode:")
            print("     [1] Enhance video (output as video)")
            print("     [2] Extract audio only (output as audio file)")
            while True:
                choice = input("  > Your choice (1/2): ").strip()
                if choice == "1":
                    extract_audio_flag = False
                    break
                elif choice == "2":
                    extract_audio_flag = True
                    break
                print("    [!] Invalid choice. Enter 1 or 2.")
    else:
        extract_audio_flag = False

    if is_video and not extract_audio_flag:
        output_format = input_path.suffix
    else:
        if args.format:
            fmt = args.format.strip().lower()
            if not fmt.startswith("."):
                fmt = f".{fmt}"
            if fmt not in SUPPORTED_AUDIO_EXTENSIONS:
                print(f"\n[ERROR] Unsupported output audio format: '{fmt}'")
                print(f"        Supported: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}")
                sys.exit(1)
            output_format = fmt
        else:
            default_ext = ".mp3" if is_video else input_path.suffix
            output_format = prompt_for_format(default_ext)

    speed = args.speed or prompt_for_speed()

    file_type_label = "video" if is_video else "audio"
    if is_video and extract_audio_flag:
        file_type_label = f"video (extracting audio to {output_format})"
    elif not is_video and output_format != input_path.suffix:
        file_type_label = f"audio (converting to {output_format})"

    ai_label = " + AI filler removal" if args.use_ai else ""
    print(f"\n  Summary:")
    print(f"     Source : {input_path.name} ({file_type_label})")
    print(f"     Speed  : {speed}x")
    print(f"     Mode   : Local DSP{ai_label}")

    with tempfile.TemporaryDirectory(prefix="kavara_") as temp_dir:
        ctx = EnhancerContext(
            input_path=input_path,
            speed=speed,
            use_ai=args.use_ai,
            is_video=is_video,
            extract_audio=extract_audio_flag,
            output_format=output_format,
            temp_dir=temp_dir,
        )
        run_pipeline(ctx)


if __name__ == "__main__":
    main()
