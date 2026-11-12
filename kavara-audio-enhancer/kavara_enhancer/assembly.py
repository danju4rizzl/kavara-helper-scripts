"""Final assembly: encode audio or remux with video."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .captions import ass_filter
from .cutting import generate_cut_filter
from .constants import VIDEO_X264_CRF, VIDEO_X264_PRESET
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
    video_preset: str = VIDEO_X264_PRESET,
    video_crf: str = VIDEO_X264_CRF,
    caption_file: Optional[Path] = None,
) -> None:
    """Remux enhanced audio back into original video when no AI video cuts are needed.

    Burning captions needs a re-encode, so the stream-copy fast path is only used without them.
    """
    if speed == 1.0 and caption_file is None:
        run_ffmpeg(
            ["-i", str(input_video), "-i", enhanced_audio_wav,
             "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0",
             "-c:a", "aac", "-b:a", "192k",
             "-shortest", str(output_path)],
            description="video remuxing (stream copy)",
        )
    else:
        video_filters = []
        if speed != 1.0:
            video_filters.append(f"setpts={1.0 / speed:.4f}*PTS")
        if caption_file is not None:
            video_filters.append(ass_filter(caption_file))
        run_ffmpeg(
            ["-i", str(input_video), "-i", enhanced_audio_wav,
             "-filter_complex",
             f"[0:v]{','.join(video_filters)}[outv]",
             "-map", "[outv]", "-map", "1:a:0",
             "-c:v", "libx264", "-preset", video_preset, "-crf", video_crf,
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
    video_preset: str = VIDEO_X264_PRESET,
    video_crf: str = VIDEO_X264_CRF,
    caption_file: Optional[Path] = None,
) -> None:
    """Cut and speed-adjust video stream, then mux with enhanced audio in a single pass.

    Captions (already on the edited timeline) are drawn in the same pass, after cuts and speed.
    """
    filtergraph = generate_cut_filter(
        cuts=cuts,
        total_duration=total_duration,
        video_stream=True,
        audio_stream=False,
        speed_factor=speed,
    )
    if caption_file is not None:
        filtergraph += f";[outv]{ass_filter(caption_file)}[capv]"
    run_ffmpeg(
        ["-i", str(input_video), "-i", enhanced_audio_wav,
         "-filter_complex", filtergraph,
         "-map", "[capv]" if caption_file is not None else "[outv]", "-map", "1:a:0",
         "-c:v", "libx264", "-preset", video_preset, "-crf", video_crf,
         "-c:a", "aac", "-b:a", "192k",
         "-shortest", str(output_path)],
        description="final video assembly with AI cuts",
    )
