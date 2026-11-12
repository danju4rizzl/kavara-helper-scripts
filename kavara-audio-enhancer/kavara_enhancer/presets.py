"""Ready-made setups: Balanced (recommended), Fast, or Custom (choose every option yourself)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .denoise import ENGINE_SPECTRAL

PRESET_BALANCED = "balanced"
PRESET_FAST = "fast"
PRESET_CUSTOM = "custom"
PRESET_CHOICES = (PRESET_BALANCED, PRESET_FAST, PRESET_CUSTOM)


@dataclass(frozen=True)
class Preset:
    """Everything a preset decides. Playback speed, file and format are always your choice."""

    key: str
    label: str
    summary: str
    denoise_strength: float       # 0 disables noise reduction
    denoise_engine: str
    normalize: bool               # loudness target stays automatic: -14 LUFS video, -16 LUFS audio
    cut_silence: bool             # local FFmpeg silence removal
    use_ai: bool                  # Gemini transcript: remove fillers, repeats and restarts
    generate_subtitles: bool
    burn_captions: bool           # draw captions into video output (needs generate_subtitles)
    video_preset: str             # x264 speed/size trade-off for the final video encode
    video_crf: str                # x264 quality (lower = better quality, bigger file)


PRESETS: dict[str, Preset] = {
    PRESET_BALANCED: Preset(
        key=PRESET_BALANCED,
        label="Balanced",
        summary="Best results: silence + filler/repeat removal (AI), light denoise, loudness, burned-in captions, high-quality video",
        denoise_strength=0.40, denoise_engine=ENGINE_SPECTRAL, normalize=True,
        cut_silence=True, use_ai=True, generate_subtitles=True, burn_captions=True,
        video_preset="veryfast", video_crf="20",
    ),
    PRESET_FAST: Preset(
        key=PRESET_FAST,
        label="Fast",
        summary="Quickest: local silence removal + loudness only (no AI, no denoise); larger video file",
        denoise_strength=0.0, denoise_engine=ENGINE_SPECTRAL, normalize=True,
        cut_silence=True, use_ai=False, generate_subtitles=False, burn_captions=False,
        video_preset="ultrafast", video_crf="23",
    ),
}


def get_preset(key: Optional[str]) -> Optional[Preset]:
    """Return the preset for ``key``; None means Custom (or no preset chosen)."""
    return PRESETS.get((key or "").lower())
