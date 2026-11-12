"""Final assembly: encode audio or remux with video."""

from __future__ import annotations

from pathlib import Path

from .cutting import generate_cut_filter
from .models import CutSegment
from .system import run_ffmpeg


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
