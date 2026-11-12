import pytest

from kavara_enhancer.gemini_config import set_active_model


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path_factory):
    """Keep tests independent of the developer's real settings and secrets.

    - never read a real .env file (cli.main calls load_dotenv at startup)
    - no inherited Gemini key / model overrides
    - no accidental use of a locally downloaded RNNoise model
    - reset the process-wide active Gemini model between tests
    """
    monkeypatch.setattr("kavara_enhancer.cli.load_dotenv", lambda *args, **kwargs: False)
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "KAVARA_RNNOISE_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KAVARA_MODELS_DIR", str(tmp_path_factory.mktemp("empty_models")))
    set_active_model(None)
    yield
    set_active_model(None)
