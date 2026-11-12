import shutil
import subprocess

import pytest

from kavara_enhancer.cutting import apply_cuts_audio_only, sanitize_cuts
from kavara_enhancer.models import CutSegment
from kavara_enhancer.silence import detect_silences, parse_silencedetect, silences_to_cuts

SAMPLE = """
[silencedetect @ 0000] silence_start: 1.5
[silencedetect @ 0000] silence_end: 2.75 | silence_duration: 1.25
[silencedetect @ 0000] silence_start: -0.0012
[silencedetect @ 0000] silence_end: 0.4 | silence_duration: 0.4
[silencedetect @ 0000] silence_start: 8.2
"""


def test_parse_pairs_and_trailing_open_silence():
    # A slightly negative start is clamped to 0; an unterminated silence runs to the end.
    result = parse_silencedetect(SAMPLE, total_duration=10.0)
    assert result == [(1.5, 2.75), (0.0, 0.4), (8.2, 10.0)]


def test_parse_empty_output():
    assert parse_silencedetect("", 10.0) == []


def test_parse_ignores_trailing_start_at_or_after_end_of_file():
    assert parse_silencedetect("silence_start: 10.0", 10.0) == []


def test_silences_to_cuts_keeps_padding_and_skips_short_gaps():
    # 5.0-5.3 is too short once 0.15s is kept on each side; 6.0-6.4 leaves a 0.1s cut.
    cuts = silences_to_cuts([(1.0, 2.0), (5.0, 5.3), (6.0, 6.4)], padding=0.15)
    flat = [value for c in cuts for value in (c.start_time, c.end_time)]
    assert flat == pytest.approx([1.15, 1.85, 6.15, 6.25])


# --- Integration tests ------------------------------------------------------

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not installed"
)


def _tone_silence_tone(path):
    """2s tone + 2s digital silence + 2s tone."""
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=44100:duration=2",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=2",
         "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=44100:duration=2",
         "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1[o]", "-map", "[o]",
         "-ac", "1", "-acodec", "pcm_s16le", str(path)],
        check=True,
    )


def _duration(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out)


@needs_ffmpeg
def test_detects_the_silent_gap_with_padding(tmp_path):
    wav = tmp_path / "gap.wav"
    _tone_silence_tone(wav)
    cuts = detect_silences(str(wav), total_duration=6.0)
    assert len(cuts) == 1
    assert cuts[0].start_time == pytest.approx(2.15, abs=0.1)
    assert cuts[0].end_time == pytest.approx(3.85, abs=0.1)


@needs_ffmpeg
def test_applying_cuts_shortens_audio_by_the_removed_amount(tmp_path):
    src, dst = tmp_path / "gap.wav", tmp_path / "cut.wav"
    _tone_silence_tone(src)
    cuts = sanitize_cuts(detect_silences(str(src), 6.0), 6.0)
    removed = sum(c.end_time - c.start_time for c in cuts)
    apply_cuts_audio_only(str(src), str(dst), cuts, 6.0)
    assert _duration(dst) == pytest.approx(6.0 - removed, abs=0.05)


@needs_ffmpeg
def test_cut_graph_with_fades_runs_in_ffmpeg(tmp_path):
    src, dst = tmp_path / "gap.wav", tmp_path / "cut.wav"
    _tone_silence_tone(src)
    apply_cuts_audio_only(str(src), str(dst), [CutSegment(1.0, 1.2), CutSegment(3.0, 3.1)], 6.0)
    assert _duration(dst) == pytest.approx(5.7, abs=0.05)
