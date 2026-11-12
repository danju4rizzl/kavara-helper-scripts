import hashlib
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from kavara_enhancer import denoise
from kavara_enhancer.cli import build_argument_parser, prepare_denoise_engine, resolve_execution_contexts
from kavara_enhancer.denoise import (
    DenoiseEngineError,
    build_arnndn_filter,
    deepfilternet_atten_limit,
    denoise_audio,
    download_rnnoise_model,
    engine_unavailable_reason,
    quote_filter_value,
    resolve_rnnoise_model,
)


# --- filter building ------------------------------------------------------------

def test_arnndn_filter_quotes_the_path_and_maps_strength_to_mix():
    assert build_arnndn_filter(Path("/models/sh.rnnn"), 0.8) == "arnndn=m='/models/sh.rnnn':mix=0.8"
    assert build_arnndn_filter(Path("/m/x.rnnn"), 7).endswith(":mix=1")
    assert build_arnndn_filter(Path("/m/x.rnnn"), -3).endswith(":mix=0")


def test_quote_filter_value_escapes_for_both_ffmpeg_parsing_levels():
    assert quote_filter_value("it's here") == "'it\\'\\''s here'"
    assert quote_filter_value("C:/models/sh.rnnn") == "'C\\:/models/sh.rnnn'"  # Windows drive colon
    assert quote_filter_value("a\\b") == "'a\\\\b'"


@pytest.mark.parametrize("strength,limit", [(1.0, None), (0.95, None), (0.8, 24.0), (0.5, 15.0), (0.0, 0.0), (-1, 0.0)])
def test_deepfilternet_attenuation_limit(strength, limit):
    assert deepfilternet_atten_limit(strength) == limit


# --- model discovery ------------------------------------------------------------

def test_explicit_model_must_exist(tmp_path):
    with pytest.raises(DenoiseEngineError):
        resolve_rnnoise_model(tmp_path / "missing.rnnn")
    model = tmp_path / "m.rnnn"
    model.write_bytes(b"x")
    assert resolve_rnnoise_model(model) == model


def test_model_from_environment_variable(tmp_path, monkeypatch):
    model = tmp_path / "env.rnnn"
    model.write_bytes(b"x")
    monkeypatch.setenv("KAVARA_RNNOISE_MODEL", str(model))
    assert resolve_rnnoise_model() == model
    monkeypatch.setenv("KAVARA_RNNOISE_MODEL", str(tmp_path / "gone.rnnn"))
    with pytest.raises(DenoiseEngineError):
        resolve_rnnoise_model()


def test_model_from_cache_dir_or_none(tmp_path, monkeypatch):
    monkeypatch.setenv("KAVARA_MODELS_DIR", str(tmp_path))
    assert resolve_rnnoise_model() is None
    (tmp_path / denoise.RNNOISE_MODEL_NAME).write_bytes(b"x")
    assert resolve_rnnoise_model() == tmp_path / denoise.RNNOISE_MODEL_NAME


# --- download -------------------------------------------------------------------

class FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, limit=-1):
        return self._data if limit < 0 else self._data[:limit]


def fake_urlopen(monkeypatch, data: bytes):
    monkeypatch.setattr(denoise.urllib.request, "urlopen", lambda url, timeout=None: FakeResponse(data))


def test_download_verifies_checksum_and_saves(tmp_path, monkeypatch):
    payload = b"fake model bytes"
    fake_urlopen(monkeypatch, payload)
    target = tmp_path / "models" / "sh.rnnn"
    saved = download_rnnoise_model(target, expected_sha256=hashlib.sha256(payload).hexdigest())
    assert saved == target and target.read_bytes() == payload
    assert not list(target.parent.glob("*.part"))


def test_download_rejects_checksum_mismatch_and_saves_nothing(tmp_path, monkeypatch):
    fake_urlopen(monkeypatch, b"tampered")
    target = tmp_path / "sh.rnnn"
    with pytest.raises(DenoiseEngineError, match="checksum"):
        download_rnnoise_model(target)
    assert not target.exists()
    assert not list(tmp_path.glob("*.part"))


def test_download_refuses_plain_http(tmp_path):
    with pytest.raises(DenoiseEngineError, match="HTTPS"):
        download_rnnoise_model(tmp_path / "x", url="http://example.com/m.rnnn")


def test_download_reports_network_errors(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(denoise.urllib.request, "urlopen", boom)
    with pytest.raises(DenoiseEngineError, match="offline"):
        download_rnnoise_model(tmp_path / "x")


def test_pinned_checksum_looks_like_sha256():
    assert re.fullmatch(r"[0-9a-f]{64}", denoise.RNNOISE_MODEL_SHA256)


# --- availability ---------------------------------------------------------------

def test_spectral_is_always_available():
    assert engine_unavailable_reason("spectral") is None


def test_rnnoise_availability_messages(monkeypatch, tmp_path):
    monkeypatch.setattr(denoise, "ffmpeg_has_arnndn", lambda: False)
    assert "arnndn" in engine_unavailable_reason("rnnoise", tmp_path / "m")
    monkeypatch.setattr(denoise, "ffmpeg_has_arnndn", lambda: True)
    assert "--download-rnnoise-model" in engine_unavailable_reason("rnnoise", None)
    assert engine_unavailable_reason("rnnoise", tmp_path / "m") is None


def test_deepfilternet_availability(monkeypatch):
    monkeypatch.setattr(denoise.importlib.util, "find_spec", lambda name: None)
    assert "pip install deepfilternet" in engine_unavailable_reason("deepfilternet")
    monkeypatch.setattr(denoise.importlib.util, "find_spec", lambda name: object())
    assert engine_unavailable_reason("deepfilternet") is None
    assert "Unknown" in engine_unavailable_reason("magic")


# --- dispatcher -----------------------------------------------------------------

def test_zero_strength_copies_input(tmp_path):
    src, dst = tmp_path / "a.wav", tmp_path / "b.wav"
    src.write_bytes(b"audio")
    denoise_audio(str(src), str(dst), 0.0, engine="rnnoise")
    assert dst.read_bytes() == b"audio"


def test_dispatcher_errors(tmp_path):
    src = tmp_path / "a.wav"
    src.write_bytes(b"audio")
    with pytest.raises(DenoiseEngineError):
        denoise_audio(str(src), str(tmp_path / "o.wav"), 0.5, engine="rnnoise", rnnoise_model=None)
    with pytest.raises(DenoiseEngineError):
        denoise_audio(str(src), str(tmp_path / "o.wav"), 0.5, engine="nope")


def test_spectral_engine_delegates_to_reduce_noise(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(denoise, "reduce_noise", lambda i, o, s: calls.append((i, o, s)))
    denoise_audio("in.wav", "out.wav", 0.7, engine="spectral")
    assert calls == [("in.wav", "out.wav", 0.7)]


def test_deepfilternet_engine_with_a_stubbed_package(tmp_path, monkeypatch):
    """DeepFilterNet itself needs PyTorch; verify our glue with a stand-in `df` package."""
    seen = {}

    class State:
        def sr(self):
            return 48000

    def init_df():
        return "model", State(), None

    def load_audio(path, sr):
        seen["load"] = (path, sr)
        return "audio-tensor", None

    def enhance(model, state, audio, atten_lim_db=None):
        seen["enhance"] = (model, audio, atten_lim_db)
        return "enhanced-tensor"

    def save_audio(path, audio, sr):
        seen["save"] = (path, audio, sr)
        Path(path).write_bytes(b"out")

    package = types.ModuleType("df")
    enhance_module = types.ModuleType("df.enhance")
    enhance_module.init_df, enhance_module.load_audio = init_df, load_audio
    enhance_module.enhance, enhance_module.save_audio = enhance, save_audio
    monkeypatch.setitem(sys.modules, "df", package)
    monkeypatch.setitem(sys.modules, "df.enhance", enhance_module)

    out = tmp_path / "out.wav"
    denoise_audio("in.wav", str(out), 0.8, engine="deepfilternet")
    assert seen["load"] == ("in.wav", 48000)
    assert seen["enhance"] == ("model", "audio-tensor", 24.0)
    assert seen["save"] == (str(out), "enhanced-tensor", 48000)
    assert out.read_bytes() == b"out"


def test_deepfilternet_missing_package_is_a_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "df", None)
    monkeypatch.setitem(sys.modules, "df.enhance", None)
    with pytest.raises(DenoiseEngineError, match="pip install deepfilternet"):
        denoise_audio("in.wav", "out.wav", 0.8, engine="deepfilternet")


# --- CLI wiring ------------------------------------------------------------------

def test_cli_flags_parse():
    args = build_argument_parser().parse_args(
        ["a.wav", "--denoise-engine", "rnnoise", "--rnnoise-model", "m.rnnn", "--model", "x"]
    )
    assert (args.denoise_engine, args.rnnoise_model, args.model) == ("rnnoise", "m.rnnn", "x")
    with pytest.raises(SystemExit):
        build_argument_parser().parse_args(["--denoise-engine", "bogus"])


def test_prepare_engine_exits_when_unavailable(monkeypatch):
    monkeypatch.setattr(denoise, "ffmpeg_has_arnndn", lambda: True)
    with pytest.raises(SystemExit) as exc:
        prepare_denoise_engine("rnnoise", None, interactive=False)
    assert exc.value.code == 1


def test_prepare_engine_exits_for_missing_explicit_model(tmp_path):
    with pytest.raises(SystemExit):
        prepare_denoise_engine("rnnoise", str(tmp_path / "nope.rnnn"), interactive=False)


def test_prepare_engine_interactive_offers_download(monkeypatch, tmp_path):
    target = tmp_path / "sh.rnnn"
    monkeypatch.setenv("KAVARA_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(denoise, "ffmpeg_has_arnndn", lambda: True)
    monkeypatch.setattr("kavara_enhancer.cli.ffmpeg_has_arnndn", lambda: True)
    monkeypatch.setattr("kavara_enhancer.cli.prompt_yes_no", lambda *a, **k: True)
    def fake_download():
        target.write_bytes(b"m")
        return target

    monkeypatch.setattr("kavara_enhancer.cli.download_rnnoise_model", fake_download)
    assert prepare_denoise_engine("rnnoise", None, interactive=True) == target


def test_rnnoise_model_flag_implies_the_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(denoise, "ffmpeg_has_arnndn", lambda: True)
    clip, model = tmp_path / "a.wav", tmp_path / "m.rnnn"
    clip.write_bytes(b"")
    model.write_bytes(b"m")
    args = build_argument_parser().parse_args(["-f", str(clip), "--rnnoise-model", str(model), "--no-normalize"])
    (ctx,) = resolve_execution_contexts(args)
    assert ctx.denoise_engine == "rnnoise" and ctx.rnnoise_model == model


def test_default_engine_is_spectral_and_no_denoise_skips_validation(tmp_path):
    clip = tmp_path / "a.wav"
    clip.write_bytes(b"")
    args = build_argument_parser().parse_args(["-f", str(clip), "--no-normalize"])
    (ctx,) = resolve_execution_contexts(args)
    assert ctx.denoise_engine == "spectral"

    args = build_argument_parser().parse_args(["-f", str(clip), "--no-denoise", "--denoise-engine", "deepfilternet"])
    (ctx,) = resolve_execution_contexts(args)  # strength 0 -> engine never validated or used
    assert ctx.denoise_strength == 0.0


# --- Real FFmpeg integration (needs ffmpeg with arnndn AND a model on disk) -------

def _find_model():
    try:
        return resolve_rnnoise_model()
    except DenoiseEngineError:
        return None


# Resolved at import time, before the autouse fixture isolates KAVARA_MODELS_DIR for each test.
REAL_MODEL = _find_model()

needs_rnnoise = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and denoise.ffmpeg_has_arnndn() and REAL_MODEL),
    reason="needs ffmpeg with arnndn and a downloaded RNNoise model (run --download-rnnoise-model)",
)


def _mean_volume_db(path) -> float:
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    ).stderr
    return float(re.search(r"mean_volume:\s*(-?[\d.]+) dB", err).group(1))


@pytest.fixture
def noisy_wav(tmp_path):
    path = tmp_path / "noise.wav"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "anoisesrc=d=3:c=pink:r=44100:a=0.1", "-ac", "1", "-acodec", "pcm_s16le", str(path)],
        check=True,
    )
    return path


@needs_rnnoise
def test_rnnoise_reduces_noise_with_real_ffmpeg(noisy_wav, tmp_path):
    out = tmp_path / "clean.wav"
    denoise_audio(str(noisy_wav), str(out), 1.0, engine="rnnoise", rnnoise_model=REAL_MODEL)
    assert out.exists()
    assert _mean_volume_db(out) < _mean_volume_db(noisy_wav) - 3


@needs_rnnoise
def test_rnnoise_works_from_a_path_with_spaces_and_quotes(noisy_wav, tmp_path):
    odd_dir = tmp_path / "it's a dir, with [odd] chars"
    odd_dir.mkdir()
    model = odd_dir / "sh.rnnn"
    shutil.copy(REAL_MODEL, model)
    out = tmp_path / "clean.wav"
    denoise_audio(str(noisy_wav), str(out), 0.8, engine="rnnoise", rnnoise_model=model)
    assert out.exists() and out.stat().st_size > 0
