"""detect_cuts orchestration, with the FFmpeg/Gemini boundaries mocked out."""

from pathlib import Path

import pytest

from kavara_enhancer import pipeline
from kavara_enhancer.models import CutSegment, EnhancerContext, TimedWord


def make_ctx(**kwargs):
    return EnhancerContext(input_path=Path("a.wav"), temp_dir="tmp", **kwargs)


@pytest.fixture
def stub_io(monkeypatch):
    calls = {"transcribed": 0}

    monkeypatch.setattr(pipeline, "detect_silences", lambda *a, **k: [CutSegment(1.0, 2.0)])
    monkeypatch.setattr(pipeline, "create_analysis_payload", lambda *a, **k: "payload.mp3")

    def fake_transcribe(path, temp_dir, max_workers=4, purpose="audio"):
        calls["transcribed"] += 1
        return [
            TimedWord("so", 0.0, 0.3), TimedWord("um", 1.5, 2.5), TimedWord("yes", 3.0, 3.3),
            TimedWord("uh", 5.0, 5.4),
        ]

    monkeypatch.setattr(pipeline, "transcribe_words", fake_transcribe)
    return calls


def pairs(cuts):
    return [(c.start_time, c.end_time) for c in cuts]


def test_no_detection_enabled_returns_nothing(stub_io):
    assert pipeline.detect_cuts(make_ctx(), "raw.wav", 10.0) == []


def test_local_silence_only(stub_io):
    assert pairs(pipeline.detect_cuts(make_ctx(cut_silence=True), "raw.wav", 10.0)) == [(1.0, 2.0)]
    assert stub_io["transcribed"] == 0  # AI never called


def test_ai_fillers_come_from_transcript_and_are_merged(stub_io):
    cuts = pipeline.detect_cuts(make_ctx(use_ai=True), "raw.wav", 10.0)
    assert stub_io["transcribed"] == 1
    assert pairs(cuts) == [(1.0, 2.5), (5.0, 5.4)]  # overlapping silence + filler merged


def test_ai_failure_falls_back_to_local_cuts(stub_io, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(pipeline, "transcribe_words", boom)
    cuts = pipeline.detect_cuts(make_ctx(use_ai=True), "raw.wav", 10.0)
    assert pairs(cuts) == [(1.0, 2.0)]


def test_ai_timestamps_beyond_file_are_clamped_or_dropped(stub_io, monkeypatch):
    monkeypatch.setattr(pipeline, "detect_silences", lambda *a, **k: [])
    monkeypatch.setattr(
        pipeline, "transcribe_words",
        lambda *a, **k: [TimedWord("um", 9.8, 15.0), TimedWord("uh", 20, 21)],
    )
    cuts = pipeline.detect_cuts(make_ctx(use_ai=True), "raw.wav", 10.0)
    assert pairs(cuts) == [(9.8, 10.0)]


def test_cuts_removing_most_of_the_file_are_discarded(stub_io, monkeypatch):
    monkeypatch.setattr(pipeline, "detect_silences", lambda *a, **k: [CutSegment(0.5, 9.5)])
    assert pipeline.detect_cuts(make_ctx(cut_silence=True), "raw.wav", 10.0) == []


def test_cuts_and_subtitles_share_one_transcript(stub_io):
    ctx = make_ctx(use_ai=True, generate_subtitles=True)
    pipeline.detect_cuts(ctx, "raw.wav", 10.0)
    pipeline.ensure_transcript(ctx, "raw.wav")  # what the subtitle step calls
    assert stub_io["transcribed"] == 1


def test_failed_transcript_is_not_retried_for_subtitles(stub_io, monkeypatch):
    attempts = []

    def boom(*a, **k):
        attempts.append(1)
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(pipeline, "transcribe_words", boom)
    ctx = make_ctx(use_ai=True, generate_subtitles=True)
    pipeline.detect_cuts(ctx, "raw.wav", 10.0)
    with pytest.raises(RuntimeError, match="quota exceeded"):
        pipeline.ensure_transcript(ctx, "raw.wav")
    assert len(attempts) == 1
