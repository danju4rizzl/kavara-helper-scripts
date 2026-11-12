from pathlib import Path

import pytest

from kavara_enhancer.models import EnhancerContext
from kavara_enhancer.system import classify_input_file, find_local_media_files, is_supported_file
from kavara_enhancer.ui import format_duration, format_file_size


@pytest.mark.parametrize(
    "size,expected",
    [(0, "0 B"), (1023, "1023 B"), (1024, "1.0 KB"), (1536, "1.5 KB"), (1024**2, "1.0 MB"), (5 * 1024**3, "5.00 GB")],
)
def test_format_file_size(size, expected):
    assert format_file_size(size) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "00:00"), (59.6, "01:00"), (125, "02:05"), (3600, "1:00:00"), (3725, "1:02:05")],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


def test_output_path_video_keeps_container(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    ctx = EnhancerContext(input_path=Path("lecture.mkv"), is_video=True, output_format=".mkv")
    assert ctx.output_path == tmp_path / "enhanced_files" / "lecture_enhanced.mkv"


def test_output_path_extract_audio_defaults_to_mp3(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    ctx = EnhancerContext(input_path=Path("lecture.mp4"), is_video=True, extract_audio=True)
    assert ctx.output_path == tmp_path / "enhanced_files" / "lecture_enhanced.mp3"


def test_output_format_without_dot_is_normalised(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    ctx = EnhancerContext(input_path=Path("a.wav"), output_format="flac")
    assert ctx.output_path.name == "a_enhanced.flac"


def test_is_supported_file_is_case_insensitive():
    assert is_supported_file(Path("clip.MP4"))
    assert is_supported_file(Path("song.Mp3"))
    assert not is_supported_file(Path("notes.txt"))


def test_classify_input_file():
    assert classify_input_file(Path("a.mkv")) is True
    assert classify_input_file(Path("a.wav")) is False
    with pytest.raises(SystemExit):
        classify_input_file(Path("a.xyz"))


def test_find_local_media_files_excludes_outputs_and_sorts(tmp_path):
    for name in ["b.mp3", "A.mp4", "a_enhanced.mp3", "notes.txt"]:
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "folder.mp3").mkdir()
    assert [p.name for p in find_local_media_files(tmp_path)] == ["A.mp4", "b.mp3"]
