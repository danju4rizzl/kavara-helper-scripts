import pytest

from kavara_enhancer.cli import build_argument_parser, resolve_execution_contexts
from kavara_enhancer.constants import DEFAULT_GEMINI_MODEL, GEMINI_MODEL_LABEL
from kavara_enhancer.gemini_config import (
    active_model,
    gemini_label,
    model_label_from_id,
    resolve_model,
    set_active_model,
)


@pytest.mark.parametrize(
    "model_id,label",
    [
        ("gemini-2.5-flash", "Gemini 2.5 Flash"),
        ("models/gemini-3.5-transcribe", "Gemini 3.5 Transcribe"),
        ("gemini-3.7-flash-preview", "Gemini 3.7 Flash Preview"),
        ("  gemini_pro  ", "Gemini Pro"),
        ("", "Gemini"),
    ],
)
def test_label_from_id(model_id, label):
    assert model_label_from_id(model_id) == label


def test_resolve_model_precedence(monkeypatch):
    assert resolve_model(None) == DEFAULT_GEMINI_MODEL
    monkeypatch.setenv("GEMINI_MODEL", "from-env")
    assert resolve_model(None) == "from-env"
    assert resolve_model("from-cli") == "from-cli"
    assert resolve_model("   ") == "from-env"
    assert resolve_model("models/prefixed") == "prefixed"


def test_active_model_and_label_follow_selection(monkeypatch):
    assert active_model() == DEFAULT_GEMINI_MODEL
    assert gemini_label() == GEMINI_MODEL_LABEL

    assert set_active_model("gemini-2.5-flash") == "gemini-2.5-flash"
    assert gemini_label() == "Gemini 2.5 Flash"

    set_active_model(None)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-9-ultra")
    assert active_model() == "gemini-9-ultra"
    assert gemini_label() == "Gemini 9 Ultra"


def test_model_flag_reaches_the_active_model(tmp_path, monkeypatch):
    clip = tmp_path / "a.wav"
    clip.write_bytes(b"")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    args = build_argument_parser().parse_args(
        ["-f", str(clip), "--model", "gemini-2.5-flash", "--use-ai", "--no-denoise", "--no-normalize"]
    )
    contexts = resolve_execution_contexts(args)
    assert contexts is not None and contexts[0].use_ai
    assert active_model() == "gemini-2.5-flash"
    assert gemini_label() == "Gemini 2.5 Flash"
