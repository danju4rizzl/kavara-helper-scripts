from kavara_enhancer.models import SubtitleEntry
from kavara_enhancer.subtitles import (
    format_timestamp_srt,
    format_timestamp_vtt,
    render_srt,
    render_txt,
    render_vtt,
    save_subtitle_files,
)

ENTRIES = [
    SubtitleEntry(1, 0.0, 2.5, "Hello world."),
    SubtitleEntry(2, 3723.456, 3726.0, "Over an hour in."),
]


def test_srt_timestamp_uses_comma():
    assert format_timestamp_srt(3723.456) == "01:02:03,456"


def test_vtt_timestamp_uses_dot():
    assert format_timestamp_vtt(3723.456) == "01:02:03.456"


def test_negative_timestamp_clamps_to_zero():
    assert format_timestamp_srt(-5) == "00:00:00,000"


def test_timestamp_carries_into_next_minute():
    assert format_timestamp_srt(59.9996) == "00:01:00,000"


def test_render_srt():
    assert render_srt(ENTRIES) == (
        "1\n00:00:00,000 --> 00:00:02,500\nHello world.\n\n"
        "2\n01:02:03,456 --> 01:02:06,000\nOver an hour in.\n"
    )


def test_render_vtt_has_header():
    out = render_vtt(ENTRIES)
    assert out.startswith("WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.500\nHello world.")


def test_render_txt():
    assert render_txt(ENTRIES) == "[00:00:00.000] Hello world.\n[01:02:03.456] Over an hour in."


def test_save_subtitle_files_names_and_unknown_formats(tmp_path):
    media = tmp_path / "talk_enhanced.mp4"
    saved = save_subtitle_files(ENTRIES, media, ["srt", ".vtt", "TXT", "bogus"])
    assert [p.name for p in saved] == [
        "talk_enhanced.srt",
        "talk_enhanced.vtt",
        "talk_enhanced_transcript.txt",
    ]
    assert (tmp_path / "talk_enhanced.srt").read_text(encoding="utf-8") == render_srt(ENTRIES)
