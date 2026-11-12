"""detect_cuts orchestration, with the FFmpeg/Gemini boundaries mocked out."""

from pathlib import Path

import pytest

from kavara_enhancer import pipeline
from kavara_enhancer.models import CutSegment, EnhancerContext


def make_ctx(**kwargs):
    return EnhancerContext(input_path=Path("a.wav"), temp_dir="tmp", **kwargs)


@pytest.fixture
def stub_io(monkeypatch):
    calls = {"filler_only": None}

    monkeypatch.setattr(pipeline, "detect_silences", lambda *a, **k: [CutSegment(1.0, 2.0)])
    monkeypatch.setattr(pipeline, "create_analysis_payload", lambda *a, **k: "payload.mp3")

    def fake_ai(path, temp_dir, max_workers=4, fillers_only=False):
        calls["filler_only"] = fillers_only
        return [CutSegment(1.5, 2.5), CutSegment(5.0, 5.4)]

    monkeypatch.setattr(pipeline, "analyze_audio_with_gemini", fake_ai)
    return calls


def pairs(cuts):
    return [(c.start_time, c.end_time) for c in cuts]


def test_no_detection_enabled_returns_nothing(stub_io):
    assert pipeline.detect_cuts(make_ctx(), "raw.wav", 10.0) == []


def test_local_silence_only(stub_io):
    assert pairs(pipeline.detect_cuts(make_ctx(cut_silence=True), "raw.wav", 10.0)) == [(1.0, 2.0)]
    assert stub_io["filler_only"] is None  # AI never called


def test_ai_is_asked_for_fillers_only_and_results_are_merged(stub_io):
    cuts = pipeline.detect_cuts(make_ctx(use_ai=True), "raw.wav", 10.0)
    assert stub_io["filler_only"] is True
    assert pairs(cuts) == [(1.0, 2.5), (5.0, 5.4)]  # overlapping silence + filler merged


def test_ai_failure_falls_back_to_local_cuts(stub_io, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(pipeline, "analyze_audio_with_gemini", boom)
    cuts = pipeline.detect_cuts(make_ctx(use_ai=True), "raw.wav", 10.0)
    assert pairs(cuts) == [(1.0, 2.0)]


def test_ai_timestamps_beyond_file_are_clamped_or_dropped(stub_io, monkeypatch):
    monkeypatch.setattr(pipeline, "detect_silences", lambda *a, **k: [])
    monkeypatch.setattr(
        pipeline, "analyze_audio_with_gemini",
        lambda *a, **k: [CutSegment(9.8, 15.0), CutSegment(20, 21), CutSegment(4, 3)],
    )
    cuts = pipeline.detect_cuts(make_ctx(use_ai=True), "raw.wav", 10.0)
    assert pairs(cuts) == [(9.8, 10.0)]


def test_cuts_removing_most_of_the_file_are_discarded(stub_io, monkeypatch):
    monkeypatch.setattr(pipeline, "detect_silences", lambda *a, **k: [CutSegment(0.5, 9.5)])
    assert pipeline.detect_cuts(make_ctx(cut_silence=True), "raw.wav", 10.0) == []
