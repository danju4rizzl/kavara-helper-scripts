"""Guardrails for project rules in AGENTS.md. If one fails, read the rule before changing the test."""

from pathlib import Path

from kavara_enhancer import constants, dsp
from kavara_enhancer.models import EnhancerContext

RULES = "See AGENTS.md ('{}')."


def test_default_output_goes_to_enhanced_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctx = EnhancerContext(input_path=Path("talk.wav"))
    assert ctx.output_path == tmp_path / "enhanced_files" / "talk_enhanced.wav", RULES.format("Output")
    assert constants.DEFAULT_OUTPUT_DIR_NAME == "enhanced_files"


def test_default_denoise_is_gentle():
    assert EnhancerContext(input_path=Path("a.wav")).denoise_strength <= 0.5, RULES.format("Audio quality")


def test_uses_the_transcribe_model():
    assert constants.DEFAULT_GEMINI_MODEL == "gemini-3.5-transcribe", RULES.format("AI model")


def test_client_is_pinned_to_v1beta_and_verbatim_with_word_timestamps(monkeypatch, tmp_path):
    import inspect

    from kavara_enhancer import ai

    source = inspect.getsource(ai._transcribe_chunk)  # real source, before it is patched below
    seen = {}
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(ai, "split_audio_into_chunks", lambda *a, **k: [("a.mp3", 0.0, 1.0)])

    def fake_chunk(client, model, *a, **k):
        seen["http_options"] = client._api_client._http_options
        seen["model"] = model
        return 1, []

    monkeypatch.setattr(ai, "_transcribe_chunk", fake_chunk)
    ai.transcribe_words("a.mp3", str(tmp_path))
    assert seen["http_options"].api_version == "v1beta", RULES.format("AI model")
    assert seen["model"] == "gemini-3.5-transcribe"

    assert 'mode="VERBATIM"' in source and "word_timestamp=True" in source, RULES.format("AI model")


def test_speed_prefers_rubberband(monkeypatch):
    monkeypatch.setattr(dsp, "ffmpeg_has_filter", lambda name: True)
    assert dsp.build_speed_filter(1.5).startswith("rubberband="), RULES.format("Audio quality")


def test_pipeline_order_cuts_before_denoise_and_subtitles_last():
    import inspect
    from kavara_enhancer import pipeline

    src = inspect.getsource(pipeline.run_pipeline)
    order = [src.index(k) for k in ("detect_cuts(", "denoise_audio(", "change_speed_preserve_pitch(",
                                    "normalize_audio_loudness(", "build_subtitles_from_words(")]
    assert order == sorted(order), RULES.format("Pipeline order")


def test_agents_file_exists_and_claude_points_to_it():
    root = Path(__file__).resolve().parent.parent
    assert (root / "AGENTS.md").is_file()
    assert "@AGENTS.md" in (root / "CLAUDE.md").read_text()
