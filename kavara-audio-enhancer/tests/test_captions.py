from pathlib import Path

from kavara_enhancer import assembly
from kavara_enhancer.captions import (
    ass_filter, build_caption_chunks, render_ass, write_caption_file,
)
from kavara_enhancer.models import CutSegment, TimedWord


def words(text, start=0.0, step=0.35):
    out, t = [], start
    for w in text.split():
        out.append(TimedWord(w, t, t + 0.3))
        t += step
    return out


def test_chunks_are_short_and_never_overlap():
    chunks = build_caption_chunks(words("one two three four five six seven eight nine ten eleven twelve"))
    assert len(chunks) >= 2
    assert all(len(c.text.split()) <= 7 for c in chunks)
    assert all(a.end_time <= b.start_time for a, b in zip(chunks, chunks[1:]))
    assert " ".join(c.text for c in chunks) == "one two three four five six seven eight nine ten eleven twelve"


def test_chunks_break_on_sentence_end_and_pause():
    ws = words("Hello there.") + words("Next one", start=5.0)
    assert [c.text for c in build_caption_chunks(ws)] == ["Hello there.", "Next one"]


def test_portrait_chunks_are_narrower():
    text = "configuration management documentation infrastructure"
    assert len(build_caption_chunks(words(text), portrait=True)) > len(build_caption_chunks(words(text)))


def test_empty_and_blank_words():
    assert build_caption_chunks([]) == []
    assert build_caption_chunks([TimedWord("  ", 0, 1)]) == []


def test_ass_scales_with_video_and_escapes_override_codes():
    chunks = build_caption_chunks([TimedWord("a{b}c", 1.0, 1.5)])
    land, port = render_ass(chunks, 1920, 1080), render_ass(chunks, 1080, 1920)
    assert "PlayResX: 1920" in land and "PlayResY: 1080" in land
    assert "a(b)c" in land and "{" not in land.split("[Events]")[1].split(",,", 1)[1]
    assert "Dialogue: 0,0:00:01.00," in land
    margin = lambda ass: int(ass.split("Style: Default,")[1].splitlines()[0].split(",")[-2])
    assert margin(port) / 1920 > margin(land) / 1080  # portrait keeps clear of Shorts/Reels UI


def test_write_caption_file_goes_to_given_directory(tmp_path):
    path, count = write_caption_file(words("hello world."), 1280, 720, str(tmp_path))
    assert path == tmp_path / "captions.ass" and count == 1
    assert "hello world." in path.read_text(encoding="utf-8")


def test_ass_filter_escapes_windows_path():
    assert ass_filter(Path(r"C:\Users\me\tmp\captions.ass")) == r"ass=filename='C\:/Users/me/tmp/captions.ass'"


def _capture(monkeypatch):
    calls = []
    monkeypatch.setattr(assembly, "run_ffmpeg", lambda args, description, **k: calls.append(args))
    return calls


def test_cut_video_draws_captions_after_cuts_and_maps_them(monkeypatch, tmp_path):
    calls = _capture(monkeypatch)
    assembly.merge_cut_video_and_audio(
        tmp_path / "in.mp4", "a.wav", tmp_path / "out.mp4", [CutSegment(1, 2)], 10.0, 1.25,
        caption_file=tmp_path / "captions.ass",
    )
    args = calls[0]
    graph = args[args.index("-filter_complex") + 1]
    assert graph.index("setpts=") < graph.index("ass=") and graph.endswith("[capv]")
    assert args[args.index("-map") + 1] == "[capv]"


def test_captions_force_reencode_even_at_normal_speed(monkeypatch, tmp_path):
    calls = _capture(monkeypatch)
    assembly.merge_audio_video(tmp_path / "in.mp4", "a.wav", tmp_path / "out.mp4", 1.0)
    assert "copy" in calls[0]
    assembly.merge_audio_video(tmp_path / "in.mp4", "a.wav", tmp_path / "out.mp4", 1.0,
                               caption_file=tmp_path / "captions.ass")
    assert "copy" not in calls[1] and "libx264" in calls[1]
    assert "setpts" not in calls[1][calls[1].index("-filter_complex") + 1]


def test_no_captions_leaves_cut_command_unchanged(monkeypatch, tmp_path):
    calls = _capture(monkeypatch)
    assembly.merge_cut_video_and_audio(tmp_path / "in.mp4", "a.wav", tmp_path / "out.mp4",
                                       [CutSegment(1, 2)], 10.0, 1.0)
    args = calls[0]
    assert "ass=" not in args[args.index("-filter_complex") + 1]
    assert args[args.index("-map") + 1] == "[outv]"
