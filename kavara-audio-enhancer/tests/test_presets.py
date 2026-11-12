"""Balanced / Fast / Custom setups and how explicit flags override them."""

from pathlib import Path

import pytest

from kavara_enhancer import cli
from kavara_enhancer.cli import build_argument_parser, resolve_execution_contexts
from kavara_enhancer.presets import PRESETS, get_preset


@pytest.fixture(autouse=True)
def fake_api_key(monkeypatch):
    monkeypatch.setattr(cli, "ensure_gemini_api_key", lambda: True)


def resolve(tmp_path, *argv, name="a.mp4"):
    media = tmp_path / name
    media.write_bytes(b"")
    (ctx,) = resolve_execution_contexts(build_argument_parser().parse_args([str(media), *argv]))
    return ctx


def test_balanced_preset(tmp_path):
    ctx = resolve(tmp_path, "--preset", "balanced")
    assert (ctx.use_ai, ctx.cut_silence, ctx.generate_subtitles) == (True, True, True)
    assert ctx.burn_captions is True
    assert ctx.denoise_strength == 0.40 and ctx.normalize_lufs == -14.0  # video default
    assert (ctx.video_preset, ctx.video_crf, ctx.preset_name) == ("veryfast", "20", "balanced")


def test_fast_preset(tmp_path):
    ctx = resolve(tmp_path, "--preset", "fast")
    assert (ctx.use_ai, ctx.cut_silence, ctx.denoise_strength) == (False, True, 0.0)
    assert ctx.normalize_lufs == -14.0
    assert (ctx.video_preset, ctx.video_crf) == ("ultrafast", "23")


def test_audio_files_get_the_audio_loudness_default(tmp_path):
    assert resolve(tmp_path, "--preset", "fast", name="a.wav").normalize_lufs == -16.0


def test_explicit_flags_override_the_preset(tmp_path):
    ctx = resolve(tmp_path, "--preset", "balanced", "--no-ai", "--denoise", "70%", "--lufs", "-18", "--subtitles")
    assert (ctx.use_ai, ctx.generate_subtitles) == (False, True)
    assert ctx.denoise_strength == 0.7 and ctx.normalize_lufs == -18.0
    assert ctx.cut_silence is True  # still the preset's choice


def test_no_preset_keeps_the_existing_behaviour(tmp_path):
    ctx = resolve(tmp_path, "--cut-silence")
    assert ctx.preset_name is None
    assert (ctx.use_ai, ctx.denoise_strength) == (False, 0.40)
    assert (ctx.video_preset, ctx.video_crf) == ("veryfast", "18")


def test_custom_is_the_same_as_no_preset(tmp_path):
    ctx = resolve(tmp_path, "--preset", "custom")
    assert ctx.preset_name is None and ctx.use_ai is False


def test_balanced_without_api_key_falls_back_to_local(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ensure_gemini_api_key", lambda: False)
    ctx = resolve(tmp_path, "--preset", "balanced")
    assert ctx.use_ai is False and ctx.cut_silence is True  # silence removal still works


def test_batch_keeps_the_preset_and_per_type_loudness(tmp_path):
    (tmp_path / "a.wav").write_bytes(b"")
    (tmp_path / "b.mp4").write_bytes(b"")
    contexts = resolve_execution_contexts(
        build_argument_parser().parse_args([str(tmp_path / "a.wav"), str(tmp_path / "b.mp4"), "--preset", "fast"])
    )
    assert [c.normalize_lufs for c in contexts] == [-16.0, -14.0]
    assert {c.video_preset for c in contexts} == {"ultrafast"}


def test_get_preset():
    assert get_preset("fast") is PRESETS["fast"] and get_preset("custom") is None and get_preset(None) is None


def test_fast_preset_does_not_burn_captions(tmp_path):
    ctx = resolve(tmp_path, "--preset", "fast")
    assert (ctx.generate_subtitles, ctx.burn_captions) == (False, False)


def test_no_burn_captions_overrides_the_preset_but_keeps_subtitle_files(tmp_path):
    ctx = resolve(tmp_path, "--preset", "balanced", "--no-burn-captions")
    assert (ctx.generate_subtitles, ctx.burn_captions) == (True, False)


def test_no_subtitles_turns_off_the_presets_burn_in_too(tmp_path):
    ctx = resolve(tmp_path, "--preset", "balanced", "--no-subtitles")
    assert (ctx.generate_subtitles, ctx.burn_captions) == (False, False)


def test_burn_captions_flag_without_preset_enables_subtitles(tmp_path):
    ctx = resolve(tmp_path, "--burn-captions")
    assert (ctx.generate_subtitles, ctx.burn_captions) == (True, True)


def test_burn_captions_is_off_by_default_without_a_preset(tmp_path):
    assert resolve(tmp_path, "--cut-silence").burn_captions is False


def test_wizard_asks_about_burning_only_for_video_output(monkeypatch):
    from kavara_enhancer import prompts

    monkeypatch.setattr(prompts, "prompt_menu_choice", lambda *a, **k: "3")
    monkeypatch.setattr(prompts, "prompt_for_subtitle_formats", lambda: ["srt"])
    asked = []
    monkeypatch.setattr(prompts, "prompt_yes_no", lambda q, default=True: asked.append(q) or True)
    assert prompts.prompt_for_ai_and_subtitles(can_burn=True) == (False, True, ["srt"], True)
    assert len(asked) == 1
    assert prompts.prompt_for_ai_and_subtitles(can_burn=False)[3] is False
    assert len(asked) == 1
