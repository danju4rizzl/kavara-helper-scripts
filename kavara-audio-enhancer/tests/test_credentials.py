import os
import sys
import types

import pytest

from kavara_enhancer import credentials, prompts


@pytest.fixture
def fake_keyring(monkeypatch):
    """Install an in-memory stand-in for the optional `keyring` package."""
    store: dict[tuple[str, str], str] = {}

    module = types.ModuleType("keyring")
    module.get_password = lambda service, user: store.get((service, user))
    module.set_password = lambda service, user, value: store.__setitem__((service, user), value)

    def delete_password(service, user):
        if (service, user) not in store:
            raise KeyError("not stored")
        del store[(service, user)]

    module.delete_password = delete_password
    monkeypatch.setitem(sys.modules, "keyring", module)
    return store


@pytest.fixture
def no_keyring(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)  # makes `import keyring` raise ImportError


def test_environment_key_wins_over_keyring(monkeypatch, fake_keyring):
    fake_keyring[(credentials.KEYRING_SERVICE, credentials.KEYRING_USERNAME)] = "from-keyring"
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert credentials.find_api_key() == ("from-env", "environment / .env")


def test_keyring_is_used_and_exported_when_env_is_empty(fake_keyring):
    fake_keyring[(credentials.KEYRING_SERVICE, credentials.KEYRING_USERNAME)] = "from-keyring"
    assert credentials.find_api_key() == ("from-keyring", "system keyring")
    assert os.environ["GEMINI_API_KEY"] == "from-keyring"


def test_nothing_found(fake_keyring):
    assert credentials.find_api_key() == (None, "")


def test_keyring_roundtrip(fake_keyring):
    assert credentials.keyring_available()
    assert credentials.save_keyring_key("abc123") is True
    assert credentials.get_keyring_key() == "abc123"
    assert credentials.delete_keyring_key() is True
    assert credentials.get_keyring_key() is None
    assert credentials.delete_keyring_key() is False  # nothing left to delete


def test_everything_degrades_gracefully_without_keyring(no_keyring):
    assert credentials.keyring_available() is False
    assert credentials.get_keyring_key() is None
    assert credentials.save_keyring_key("x") is False
    assert credentials.delete_keyring_key() is False
    assert credentials.find_api_key() == (None, "")


def test_backend_errors_do_not_escape(monkeypatch):
    module = types.ModuleType("keyring")

    def broken(*args, **kwargs):
        raise RuntimeError("no backend")

    module.get_password = module.set_password = module.delete_password = broken
    monkeypatch.setitem(sys.modules, "keyring", module)
    assert credentials.get_keyring_key() is None
    assert credentials.save_keyring_key("x") is False
    assert credentials.delete_keyring_key() is False


# --- interactive helper ------------------------------------------------------

def test_ensure_key_uses_existing_env_without_prompting(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    monkeypatch.setattr(prompts.getpass, "getpass", lambda *a: pytest.fail("should not prompt"))
    assert prompts.ensure_gemini_api_key() is True


def test_ensure_key_prompts_hidden_and_can_save_to_keyring(monkeypatch, fake_keyring):
    monkeypatch.setattr(prompts.getpass, "getpass", lambda *a: "  typed-key  ")
    monkeypatch.setattr("builtins.input", lambda *a: "y")
    assert prompts.ensure_gemini_api_key() is True
    assert os.environ["GEMINI_API_KEY"] == "typed-key"
    assert fake_keyring[(credentials.KEYRING_SERVICE, credentials.KEYRING_USERNAME)] == "typed-key"


def test_ensure_key_declining_keyring_keeps_it_session_only(monkeypatch, fake_keyring):
    monkeypatch.setattr(prompts.getpass, "getpass", lambda *a: "typed-key")
    monkeypatch.setattr("builtins.input", lambda *a: "n")
    assert prompts.ensure_gemini_api_key() is True
    assert fake_keyring == {}


def test_ensure_key_without_keyring_does_not_offer_saving(monkeypatch, no_keyring):
    monkeypatch.setattr(prompts.getpass, "getpass", lambda *a: "typed-key")
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("should not ask about the keyring"))
    assert prompts.ensure_gemini_api_key() is True


def test_ensure_key_skip_returns_false(monkeypatch, no_keyring):
    monkeypatch.setattr(prompts.getpass, "getpass", lambda *a: "")
    assert prompts.ensure_gemini_api_key() is False
    assert "GEMINI_API_KEY" not in os.environ
