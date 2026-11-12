"""Noise-reduction engines: spectral gating, RNNoise (FFmpeg arnndn) and DeepFilterNet."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

from .constants import SAMPLE_RATE
from .dsp import reduce_noise
from .system import run_ffmpeg

ENGINE_SPECTRAL = "spectral"
ENGINE_RNNOISE = "rnnoise"
ENGINE_DEEPFILTERNET = "deepfilternet"
DENOISE_ENGINES = (ENGINE_SPECTRAL, ENGINE_RNNOISE, ENGINE_DEEPFILTERNET)
DEFAULT_DENOISE_ENGINE = ENGINE_SPECTRAL

ENGINE_LABELS = {
    ENGINE_SPECTRAL: "Spectral Gating",
    ENGINE_RNNOISE: "RNNoise neural",
    ENGINE_DEEPFILTERNET: "DeepFilterNet neural",
}

# RNNoise model for FFmpeg's `arnndn` filter, from https://github.com/GregorR/rnnoise-models
# ("somnolent-hogwash": a general-purpose speech model). The download is verified against
# this SHA-256 so a tampered or truncated file is rejected.
RNNOISE_MODEL_NAME = "sh.rnnn"
RNNOISE_MODEL_URL = (
    "https://raw.githubusercontent.com/GregorR/rnnoise-models/master/"
    "somnolent-hogwash-2018-09-01/sh.rnnn"
)
RNNOISE_MODEL_SHA256 = "70bb6685eb0c2a1d18e2918dca3fbfbd39317010b1802eb1b6ea73a92f3fdec0"
RNNOISE_MODEL_MAX_BYTES = 5 * 1024 * 1024


class DenoiseEngineError(RuntimeError):
    """Raised when a denoise engine cannot be used."""


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

def user_data_dir() -> Path:
    """Per-user application data directory."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "kavara-audio-enhancer"


def models_dir() -> Path:
    """Where downloaded models live (override with ``KAVARA_MODELS_DIR``)."""
    override = os.environ.get("KAVARA_MODELS_DIR")
    return Path(override).expanduser() if override else user_data_dir() / "models"


def default_rnnoise_model_path() -> Path:
    return models_dir() / RNNOISE_MODEL_NAME


def resolve_rnnoise_model(explicit: Optional[Path] = None) -> Optional[Path]:
    """Find an RNNoise model: ``--rnnoise-model``, ``KAVARA_RNNOISE_MODEL``, then the cache.

    Returns None if nothing usable is found. An explicit path that does not exist
    is an error rather than silently ignored.
    """
    if explicit is not None:
        if not explicit.is_file():
            raise DenoiseEngineError(f"RNNoise model file not found: {explicit}")
        return explicit

    env_value = os.environ.get("KAVARA_RNNOISE_MODEL")
    if env_value:
        env_path = Path(env_value).expanduser()
        if not env_path.is_file():
            raise DenoiseEngineError(f"KAVARA_RNNOISE_MODEL points to a missing file: {env_path}")
        return env_path

    cached = default_rnnoise_model_path()
    return cached if cached.is_file() else None


def download_rnnoise_model(
    destination: Optional[Path] = None,
    url: str = RNNOISE_MODEL_URL,
    expected_sha256: str = RNNOISE_MODEL_SHA256,
) -> Path:
    """Download the RNNoise model, verify its checksum and store it atomically."""
    if not url.startswith("https://"):
        raise DenoiseEngineError("Refusing to download a model over a non-HTTPS URL.")

    destination = destination or default_rnnoise_model_path()
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 (https enforced above)
            data = response.read(RNNOISE_MODEL_MAX_BYTES + 1)
    except Exception as exc:
        raise DenoiseEngineError(f"Could not download the RNNoise model: {exc}") from exc

    if len(data) > RNNOISE_MODEL_MAX_BYTES:
        raise DenoiseEngineError("RNNoise model download is unexpectedly large; refusing to save it.")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise DenoiseEngineError(
            f"RNNoise model checksum mismatch (got {digest[:12]}..., expected {expected_sha256[:12]}...). "
            "The file was not saved."
        )

    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False, suffix=".part") as handle:
        handle.write(data)
        partial = Path(handle.name)
    os.replace(partial, destination)
    return destination


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def ffmpeg_has_arnndn() -> bool:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return " arnndn " in result.stdout


def engine_unavailable_reason(engine: str, rnnoise_model: Optional[Path] = None) -> Optional[str]:
    """Return a human-readable reason the engine cannot run, or None if it is ready."""
    if engine == ENGINE_SPECTRAL:
        return None
    if engine == ENGINE_RNNOISE:
        if not ffmpeg_has_arnndn():
            return "Your FFmpeg build does not include the 'arnndn' filter (RNNoise)."
        if rnnoise_model is None:
            return (
                "No RNNoise model found. Run 'kavara-enhancer --download-rnnoise-model' "
                "or pass --rnnoise-model PATH."
            )
        return None
    if engine == ENGINE_DEEPFILTERNET:
        if importlib.util.find_spec("df") is None:
            return (
                "DeepFilterNet is not installed. Install it with "
                "'pip install deepfilternet' (requires PyTorch)."
            )
        return None
    return f"Unknown denoise engine '{engine}'."


# ---------------------------------------------------------------------------
# RNNoise (FFmpeg arnndn)
# ---------------------------------------------------------------------------

def quote_filter_value(value: str) -> str:
    """Escape a value (typically a path) for an FFmpeg filter option.

    FFmpeg parses filter arguments in two passes. First the option level, where
    ``\\``, ``'`` and ``:`` are special (the ``:`` in a Windows drive letter like
    ``C:`` would otherwise start a new option). Then the filtergraph level, handled
    by wrapping the result in single quotes.
    """
    option_level = value.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    return "'" + option_level.replace("'", "'\\''") + "'"


def build_arnndn_filter(model_path: Path, strength: float) -> str:
    """Build the ``arnndn`` filter; ``strength`` (0-1) maps to the filter's wet/dry ``mix``."""
    mix = min(max(strength, 0.0), 1.0)
    return f"arnndn=m={quote_filter_value(Path(model_path).as_posix())}:mix={mix:g}"


def denoise_rnnoise(input_wav: str, output_wav: str, strength: float, model_path: Path) -> None:
    run_ffmpeg(
        ["-i", input_wav, "-af", build_arnndn_filter(model_path, strength),
         "-acodec", "pcm_s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", output_wav],
        description="RNNoise noise reduction",
    )


# ---------------------------------------------------------------------------
# DeepFilterNet (optional, needs PyTorch)
# ---------------------------------------------------------------------------

def deepfilternet_atten_limit(strength: float) -> Optional[float]:
    """Map strength (0-1) to DeepFilterNet's attenuation limit in dB.

    Near-full strength means no limit (None); otherwise up to 30 dB of reduction.
    """
    strength = min(max(strength, 0.0), 1.0)
    if strength >= 0.95:
        return None
    return round(strength * 30.0, 1)


def denoise_deepfilternet(input_wav: str, output_wav: str, strength: float) -> None:
    try:
        from df.enhance import enhance, init_df, load_audio, save_audio
    except ImportError as exc:
        raise DenoiseEngineError(
            "DeepFilterNet is not installed. Install it with 'pip install deepfilternet'."
        ) from exc

    model, df_state, _ = init_df()
    audio, _ = load_audio(input_wav, sr=df_state.sr())
    enhanced = enhance(model, df_state, audio, atten_lim_db=deepfilternet_atten_limit(strength))
    save_audio(output_wav, enhanced, df_state.sr())


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def denoise_audio(
    input_wav: str,
    output_wav: str,
    strength: float,
    engine: str = DEFAULT_DENOISE_ENGINE,
    rnnoise_model: Optional[Path] = None,
) -> None:
    """Denoise ``input_wav`` into ``output_wav`` with the chosen engine."""
    if strength <= 0.0:
        shutil.copy2(input_wav, output_wav)
        return

    if engine == ENGINE_SPECTRAL:
        reduce_noise(input_wav, output_wav, strength)
    elif engine == ENGINE_RNNOISE:
        if rnnoise_model is None:
            raise DenoiseEngineError("RNNoise requires a model file (see --download-rnnoise-model).")
        denoise_rnnoise(input_wav, output_wav, strength, rnnoise_model)
    elif engine == ENGINE_DEEPFILTERNET:
        denoise_deepfilternet(input_wav, output_wav, strength)
    else:
        raise DenoiseEngineError(f"Unknown denoise engine '{engine}'.")
