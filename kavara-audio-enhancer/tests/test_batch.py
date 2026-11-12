import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kavara_enhancer.batch import (
    BatchResult,
    collect_input_files,
    derive_file_context,
    find_output_collisions,
    format_batch_summary,
)
from kavara_enhancer.cli import build_argument_parser, main, resolve_execution_contexts
from kavara_enhancer.models import EnhancerContext


def touch(directory: Path, *names: str) -> list[Path]:
    paths = []
    for name in names:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        paths.append(path)
    return paths


def names(paths):
    return [p.name for p in paths]


# --- collect_input_files -----------------------------------------------------------

def test_folder_expands_to_supported_media_sorted_and_skips_outputs(tmp_path):
    touch(tmp_path, "b.mp3", "A.mp4", "a_enhanced.mp3", "notes.txt", "sub/deep.wav")
    files, problems = collect_input_files([str(tmp_path)])
    assert names(files) == ["A.mp4", "b.mp3"] and problems == []


def test_glob_expansion_without_shell_help(tmp_path):
    touch(tmp_path, "one.wav", "two.wav", "three.mp3", "one_enhanced.wav")
    files, problems = collect_input_files([str(tmp_path / "*.wav")])
    assert names(files) == ["one.wav", "two.wav"] and problems == []


def test_explicit_files_are_kept_even_if_named_enhanced_and_duplicates_collapse(tmp_path):
    (explicit,) = touch(tmp_path, "x_enhanced.wav")
    files, _ = collect_input_files([str(explicit), str(explicit), str(tmp_path / "X_ENHANCED.wav")])
    assert len(files) == 1 or sys.platform != "win32"  # case-insensitive FS collapses the third entry


def test_filename_containing_glob_characters_is_a_plain_file(tmp_path):
    (clip,) = touch(tmp_path, "clip[1].wav")
    files, problems = collect_input_files([str(clip)])
    assert names(files) == ["clip[1].wav"] and problems == []


def test_problems_are_reported(tmp_path):
    (bad,) = touch(tmp_path, "notes.txt")
    empty = tmp_path / "empty"
    empty.mkdir()
    files, problems = collect_input_files(
        [str(tmp_path / "missing.wav"), str(bad), str(empty), str(tmp_path / "*.flac")]
    )
    assert files == []
    assert len(problems) == 4
    assert "not found" in problems[0] and "Unsupported" in problems[1]
    assert "folder" in problems[2] and "match" in problems[3]


def test_order_follows_the_arguments(tmp_path):
    a, b = touch(tmp_path, "a.wav", "b.wav")
    files, _ = collect_input_files([str(b), str(a)])
    assert names(files) == ["b.wav", "a.wav"]


# --- derive_file_context -------------------------------------------------------------

def make_template(**kwargs):
    defaults = dict(input_path=Path("first.mp4"), is_video=True, output_format=".mp4", normalize_lufs=-14.0)
    defaults.update(kwargs)
    return EnhancerContext(**defaults)


def test_audio_file_in_a_video_batch_keeps_its_own_format():
    ctx = derive_file_context(
        make_template(), Path("talk.wav"), extract_audio_pref=False, audio_format=None, normalize_is_default=False
    )
    assert (ctx.is_video, ctx.extract_audio, ctx.output_format) == (False, False, ".wav")


def test_video_in_an_extract_batch_uses_chosen_audio_format():
    template = make_template(extract_audio=True, output_format=".flac")
    ctx = derive_file_context(
        template, Path("lecture.mkv"), extract_audio_pref=True, audio_format=".flac", normalize_is_default=False
    )
    assert (ctx.is_video, ctx.extract_audio, ctx.output_format) == (True, True, ".flac")
    ctx = derive_file_context(
        template, Path("lecture.mkv"), extract_audio_pref=True, audio_format=None, normalize_is_default=False
    )
    assert ctx.output_format == ".mp3"


def test_video_keeps_its_container_when_not_extracting():
    ctx = derive_file_context(
        make_template(is_video=False, input_path=Path("a.wav"), output_format=".wav"),
        Path("clip.MKV"), extract_audio_pref=False, audio_format=None, normalize_is_default=False,
    )
    assert (ctx.is_video, ctx.extract_audio, ctx.output_format) == (True, False, ".MKV")


def test_default_loudness_is_recomputed_per_file_type_only_when_defaulted():
    template = make_template(normalize_lufs=-14.0)
    audio = derive_file_context(template, Path("a.wav"), extract_audio_pref=False, audio_format=None, normalize_is_default=True)
    video = derive_file_context(template, Path("a.mp4"), extract_audio_pref=False, audio_format=None, normalize_is_default=True)
    chosen = derive_file_context(template, Path("a.wav"), extract_audio_pref=False, audio_format=None, normalize_is_default=False)
    assert (audio.normalize_lufs, video.normalize_lufs, chosen.normalize_lufs) == (-16.0, -14.0, -14.0)


def test_derived_contexts_do_not_share_state():
    template = make_template()
    template.cut_segments.append(object())
    template.subtitle_formats.append("vtt")
    ctx = derive_file_context(template, Path("b.mp4"), extract_audio_pref=False, audio_format=None, normalize_is_default=False)
    assert ctx.cut_segments == [] and ctx.subtitle_formats == ["srt", "vtt"]
    ctx.subtitle_formats.append("txt")
    assert template.subtitle_formats == ["srt", "vtt"]
    assert ctx.temp_dir == "" and ctx.output_file is None


def test_output_collisions_are_detected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    one = EnhancerContext(input_path=Path("a/talk.wav"))
    two = EnhancerContext(input_path=Path("b/talk.wav"))
    three = EnhancerContext(input_path=Path("other.wav"))
    collisions = find_output_collisions([one, two, three])
    assert list(collisions.values()) == [[Path("a/talk.wav"), Path("b/talk.wav")]]
    assert find_output_collisions([one, three]) == {}


# --- resolve_execution_contexts ---------------------------------------------------------

def parse(argv):
    return build_argument_parser().parse_args(argv)


def test_resolve_builds_one_job_per_file_and_mixed_types(tmp_path):
    a, b, c = touch(tmp_path, "a.wav", "b.mp4", "c.mp3")
    contexts = resolve_execution_contexts(parse([str(a), str(b), "-f", str(c), "--no-denoise"]))
    assert names([ctx.input_path for ctx in contexts]) == ["a.wav", "b.mp4", "c.mp3"]
    assert [ctx.is_video for ctx in contexts] == [False, True, False]
    assert [ctx.normalize_lufs for ctx in contexts] == [-16.0, -14.0, -16.0]  # per-type defaults
    assert [ctx.output_path.suffix for ctx in contexts] == [".wav", ".mp4", ".mp3"]


def test_resolve_batch_applies_chosen_settings_to_all(tmp_path):
    files = touch(tmp_path, "a.wav", "b.wav")
    contexts = resolve_execution_contexts(
        parse([*map(str, files), "-s", "1.25", "--lufs", "-18", "--cut-silence", "--no-denoise", "-o", str(tmp_path / "out")])
    )
    assert {ctx.speed for ctx in contexts} == {1.25}
    assert {ctx.normalize_lufs for ctx in contexts} == {-18.0}
    assert all(ctx.cut_silence for ctx in contexts)
    assert {ctx.output_path.parent for ctx in contexts} == {(tmp_path / "out").resolve()}


def test_batch_format_flag_extracts_audio_from_videos(tmp_path):
    files = touch(tmp_path, "a.mp4", "b.mkv")
    contexts = resolve_execution_contexts(parse([*map(str, files), "--format", "flac", "--no-denoise"]))
    assert [ctx.extract_audio for ctx in contexts] == [True, True]
    assert [ctx.output_path.suffix for ctx in contexts] == [".flac", ".flac"]


def test_batch_rejects_a_single_output_file(tmp_path):
    files = touch(tmp_path, "a.wav", "b.wav")
    with pytest.raises(SystemExit):
        resolve_execution_contexts(parse([*map(str, files), "-o", str(tmp_path / "all.mp3")]))


def test_batch_rejects_colliding_outputs(tmp_path):
    files = touch(tmp_path, "x/talk.wav", "y/talk.wav")
    with pytest.raises(SystemExit):
        resolve_execution_contexts(parse([*map(str, files), "--no-denoise"]))


def test_unknown_input_exits(tmp_path):
    with pytest.raises(SystemExit):
        resolve_execution_contexts(parse([str(tmp_path / "ghost.wav")]))


def test_single_file_still_returns_a_single_job(tmp_path):
    (clip,) = touch(tmp_path, "solo.wav")
    contexts = resolve_execution_contexts(parse(["-f", str(clip), "--no-denoise"]))
    assert len(contexts) == 1


def test_intermixed_positionals_and_flags():
    args = build_argument_parser().parse_intermixed_args(["a.wav", "-s", "1.5", "b.wav", "--cut-silence"])
    assert args.inputs == ["a.wav", "b.wav"] and args.speed == 1.5 and args.cut_silence


# --- summary ----------------------------------------------------------------------------

def test_batch_summary_text():
    text = format_batch_summary([
        BatchResult(Path("a.wav"), Path("out/a_enhanced.wav"), True, 12.0),
        BatchResult(Path("b.wav"), Path("out/b_enhanced.wav"), False, 3.0, "FFmpeg failed\nmore detail"),
    ])
    assert "OK    a.wav  ->  a_enhanced.wav  (00:12)" in text
    assert "FAIL  b.wav  ->  FFmpeg failed  (00:03)" in text
    assert text.endswith("1/2 file(s) processed successfully.")


# --- end to end through main() (needs ffmpeg) ---------------------------------------------

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not installed"
)


def make_tone(path, seconds=1):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"sine=frequency=300:sample_rate=44100:duration={seconds}", str(path)],
        check=True,
    )


@needs_ffmpeg
def test_batch_continues_after_a_failure_and_reports_it(tmp_path, monkeypatch, capsys):
    good1, good2, corrupt = tmp_path / "a.wav", tmp_path / "c.wav", tmp_path / "b.wav"
    make_tone(good1)
    make_tone(good2, seconds=2)
    corrupt.write_bytes(b"this is not audio")
    out = tmp_path / "out"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv",
        ["kavara-enhancer", str(good1), str(corrupt), str(good2), "-o", str(out), "--no-denoise", "--lufs", "-16"],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert (out / "a_enhanced.wav").exists() and (out / "c_enhanced.wav").exists()
    assert not (out / "b_enhanced.wav").exists()
    printed = capsys.readouterr().out
    assert "File 1/3" in printed and "File 3/3" in printed
    assert "2/3 file(s) processed successfully." in printed


@needs_ffmpeg
def test_batch_all_success_exits_cleanly(tmp_path, monkeypatch):
    files = [tmp_path / "a.wav", tmp_path / "b.wav"]
    for f in files:
        make_tone(f)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["kavara-enhancer", str(tmp_path / "*.wav"), "-o", "out", "--no-denoise", "--no-normalize", "-s", "2"]
    )
    main()  # no SystemExit
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["a_enhanced.wav", "b_enhanced.wav"]
