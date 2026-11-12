import argparse

import pytest

from kavara_enhancer.cli import (
    build_argument_parser,
    parse_denoise_argument,
    parse_lufs_argument,
    parse_speed_argument,
    parse_subtitle_format_argument,
)


@pytest.mark.parametrize(
    "raw,expected",
    [("1.25", 1.25), ("1.5x", 1.5), ("2X", 2.0), ("1.333", 1.33), ("0.25", 0.25), ("4", 4.0)],
)
def test_speed_valid(raw, expected):
    assert parse_speed_argument(raw) == expected


@pytest.mark.parametrize("raw", ["0.1", "4.5", "fast", ""])
def test_speed_invalid(raw):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_speed_argument(raw)


@pytest.mark.parametrize(
    "raw,expected",
    [("0.8", 0.8), ("80%", 0.8), ("95", 0.95), ("0", 0.0), ("1", 1.0), ("100", 1.0)],
)
def test_denoise_valid(raw, expected):
    assert parse_denoise_argument(raw) == expected


@pytest.mark.parametrize("raw", ["101", "-1", "loud"])
def test_denoise_invalid(raw):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_denoise_argument(raw)


@pytest.mark.parametrize(
    "raw,expected",
    [("-16", -16.0), ("16", -16.0), ("-14.0 LUFS", -14.0), ("-23lufs", -23.0), ("-18.04", -18.0)],
)
def test_lufs_valid(raw, expected):
    assert parse_lufs_argument(raw) == expected


@pytest.mark.parametrize("raw", ["-80", "-1", "quiet"])
def test_lufs_invalid(raw):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_lufs_argument(raw)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("srt", ["srt"]),
        (".vtt", ["vtt"]),
        ("both", ["srt", "vtt"]),
        ("all", ["srt", "vtt", "txt"]),
        ("srt,txt", ["srt", "txt"]),
        ("nonsense", ["srt"]),
        ("  VTT ", ["vtt"]),
    ],
)
def test_subtitle_formats(raw, expected):
    assert parse_subtitle_format_argument(raw) == expected


def test_parser_aliases():
    args = build_argument_parser().parse_args(
        ["-f", "a.mp4", "--lufs=-14", "--captions", "--sub-format", "both", "-w", "8"]
    )
    assert args.file == "a.mp4"
    assert args.normalize_lufs == -14.0
    assert args.generate_subtitles is True
    assert args.subtitle_formats == ["srt", "vtt"]
    assert args.workers == 8
    assert args.speed is None
