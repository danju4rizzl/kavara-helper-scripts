import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kavara_enhancer.cli import (
    build_argument_parser,
    determine_output_mode,
    main,
    parse_output_target,
    parse_silence_threshold_argument,
)
from kavara_enhancer.models import EnhancerContext


# --- --output ---------------------------------------------------------------

def test_output_target_directory_forms(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    assert parse_output_target(str(existing)) == (existing.resolve(), None)
    assert parse_output_target(str(tmp_path / "new") + "/")[1] is None
    assert parse_output_target(str(tmp_path / "noext"))[1] is None


def test_output_target_file_form(tmp_path):
    out_dir, out_file = parse_output_target(str(tmp_path / "clean.mp3"))
    assert out_dir is None and out_file == (tmp_path / "clean.mp3").resolve()


@pytest.mark.parametrize(
    "ext,is_video,expected",
    [(".mp3", True, True), (".wav", False, False), (".mp4", True, False), (".MKV", True, False)],
)
def test_determine_output_mode(ext, is_video, expected):
    assert determine_output_mode(ext, is_video) is expected


@pytest.mark.parametrize("ext,is_video", [(".mp4", False), (".xyz", True), (".txt", False)])
def test_determine_output_mode_rejects_bad_extensions(ext, is_video):
    with pytest.raises(ValueError):
        determine_output_mode(ext, is_video)


def test_context_output_path_uses_directory(tmp_path):
    ctx = EnhancerContext(input_path=Path("talk.wav"), output_dir=tmp_path / "out")
    assert ctx.output_path == tmp_path / "out" / "talk_enhanced.wav"


def test_context_output_file_wins(tmp_path):
    target = tmp_path / "x" / "final.flac"
    ctx = EnhancerContext(input_path=Path("talk.wav"), output_file=target, output_dir=tmp_path)
    assert ctx.output_path == target


# --- silence flag -----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [("-40", -40.0), ("30", -30.0), ("-35dB", -35.0)])
def test_silence_threshold_valid(raw, expected):
    assert parse_silence_threshold_argument(raw) == expected


@pytest.mark.parametrize("raw", ["-5", "-100", "quiet"])
def test_silence_threshold_invalid(raw):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_silence_threshold_argument(raw)


def test_new_flags_parse():
    args = build_argument_parser().parse_args(
        ["-f", "a.mp3", "-o", "out/", "--cut-silence", "--silence-threshold", "-40", "--dry-run"]
    )
    assert (args.output, args.cut_silence, args.silence_threshold, args.dry_run) == ("out/", True, -40.0, True)


# --- End-to-end through main() (needs ffmpeg) -------------------------------

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not installed"
)


def _make_gappy_audio(path):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=44100:duration=2",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=2",
         "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=44100:duration=2",
         "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1[o]", "-map", "[o]", str(path)],
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
def test_dry_run_reports_cuts_and_writes_nothing(tmp_path, monkeypatch, capsys):
    src = tmp_path / "gap.wav"
    _make_gappy_audio(src)
    out_dir = tmp_path / "out"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv",
        ["kavara-enhancer", "-f", str(src), "-o", str(out_dir), "--no-denoise", "--no-normalize",
         "--cut-silence", "--dry-run"],
    )
    main()
    output = capsys.readouterr().out
    assert "DRY RUN" in output and "Planned cuts" in output and "1 cut(s)" in output
    assert not out_dir.exists()
    assert not list(tmp_path.glob("*_enhanced*"))


@needs_ffmpeg
def test_cut_silence_with_output_file_end_to_end(tmp_path, monkeypatch):
    src = tmp_path / "gap.wav"
    _make_gappy_audio(src)
    target = tmp_path / "nested" / "dir" / "clean.wav"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv",
        ["kavara-enhancer", "-f", str(src), "-o", str(target), "--no-denoise", "--no-normalize", "--cut-silence"],
    )
    main()
    assert target.exists()
    # 6s input, ~1.7s of the 2s gap removed
    assert _duration(target) == pytest.approx(4.3, abs=0.2)


@needs_ffmpeg
def test_invalid_output_extension_exits_nonzero(tmp_path, monkeypatch):
    src = tmp_path / "gap.wav"
    _make_gappy_audio(src)
    monkeypatch.setattr(sys, "argv", ["kavara-enhancer", "-f", str(src), "-o", str(tmp_path / "x.mp4")])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
