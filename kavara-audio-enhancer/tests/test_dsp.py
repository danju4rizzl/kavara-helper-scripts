import math
import shutil
import subprocess

import pytest

from kavara_enhancer.dsp import (
    build_atempo_chain,
    build_loudnorm_filter,
    change_speed_preserve_pitch,
    normalize_audio_loudness,
    parse_loudnorm_stats,
)

SAMPLE_STDERR = """
[Parsed_loudnorm_0 @ 000001]
{
	"input_i" : "-27.61",
	"input_tp" : "-4.47",
	"input_lra" : "18.06",
	"input_thresh" : "-39.20",
	"output_i" : "-16.58",
	"output_tp" : "-1.50",
	"output_lra" : "14.78",
	"output_thresh" : "-27.71",
	"normalization_type" : "dynamic",
	"target_offset" : "0.58"
}
"""


def _factors(chain: str) -> list[float]:
    return [float(part.split("=")[1]) for part in chain.split(",")]


@pytest.mark.parametrize("speed", [0.25, 0.5, 0.85, 1.0, 1.25, 1.35, 1.5, 2.0, 2.5, 3.0, 4.0])
def test_atempo_chain_multiplies_to_speed_and_stays_in_range(speed):
    factors = _factors(build_atempo_chain(speed))
    assert all(0.5 <= f <= 2.0 for f in factors)
    assert math.prod(factors) == pytest.approx(speed, rel=1e-5)


def test_atempo_chain_simple_cases():
    assert build_atempo_chain(1.5) == "atempo=1.5"
    assert build_atempo_chain(4.0) == "atempo=2,atempo=2"


def test_atempo_chain_rejects_non_positive():
    with pytest.raises(ValueError):
        build_atempo_chain(0)


def test_parse_loudnorm_stats():
    assert parse_loudnorm_stats(SAMPLE_STDERR) == {
        "input_i": -27.61,
        "input_tp": -4.47,
        "input_lra": 18.06,
        "input_thresh": -39.2,
        "target_offset": 0.58,
    }


@pytest.mark.parametrize(
    "stderr",
    ["", "no json here", '{"input_i": "-inf"}', SAMPLE_STDERR.replace("-27.61", "-inf")],
)
def test_parse_loudnorm_stats_unusable_returns_none(stderr):
    assert parse_loudnorm_stats(stderr) is None


def test_loudnorm_filter_first_pass_vs_second_pass():
    assert build_loudnorm_filter(-16.0) == "loudnorm=I=-16.0:TP=-1.5:LRA=11"
    second = build_loudnorm_filter(-16.0, parse_loudnorm_stats(SAMPLE_STDERR))
    assert second.startswith("loudnorm=I=-16.0:TP=-1.5:LRA=11:measured_I=-27.61")
    assert "offset=0.58" in second and second.endswith(":linear=true")


# --- Integration tests: need a real ffmpeg/ffprobe on PATH -----------------

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="ffmpeg/ffprobe not installed",
)


def _make_tone(path, seconds=4, volume_db=-30):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"sine=frequency=220:sample_rate=44100:duration={seconds}",
         "-af", f"volume={volume_db}dB", "-ac", "1", "-acodec", "pcm_s16le", str(path)],
        check=True,
    )


def _duration(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out)


def _integrated_loudness(path) -> float:
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    ).stderr
    summary = err[err.rindex("Integrated loudness"):]
    line = next(ln for ln in summary.splitlines() if ln.strip().startswith("I:"))
    return float(line.split()[1])


@needs_ffmpeg
@pytest.mark.parametrize("speed", [0.5, 1.5, 2.0, 3.0])
def test_change_speed_scales_duration(tmp_path, speed):
    src, dst = tmp_path / "in.wav", tmp_path / "out.wav"
    _make_tone(src, seconds=4)
    change_speed_preserve_pitch(str(src), str(dst), speed)
    assert _duration(dst) == pytest.approx(4 / speed, abs=0.1)


@needs_ffmpeg
def test_change_speed_identity_copies(tmp_path):
    src, dst = tmp_path / "in.wav", tmp_path / "out.wav"
    _make_tone(src)
    change_speed_preserve_pitch(str(src), str(dst), 1.0)
    assert dst.read_bytes() == src.read_bytes()


@needs_ffmpeg
@pytest.mark.parametrize("target", [-16.0, -14.0])
def test_normalize_hits_target_loudness(tmp_path, target):
    src, dst = tmp_path / "in.wav", tmp_path / "out.wav"
    _make_tone(src, seconds=6, volume_db=-35)
    normalize_audio_loudness(str(src), str(dst), target)
    assert _integrated_loudness(dst) == pytest.approx(target, abs=1.0)


@needs_ffmpeg
def test_normalize_silent_audio_falls_back_without_error(tmp_path):
    src, dst = tmp_path / "silence.wav", tmp_path / "out.wav"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=mono", "-t", "2", "-acodec", "pcm_s16le", str(src)],
        check=True,
    )
    normalize_audio_loudness(str(src), str(dst), -16.0)
    assert dst.exists()
