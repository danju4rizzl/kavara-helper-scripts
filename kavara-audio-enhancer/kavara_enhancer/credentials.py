"""Gemini API key lookup: environment / ``.env`` first, then the OS keyring.

Lookup order for the API key:

1. the ``GEMINI_API_KEY`` environment variable, which includes values loaded from a
   ``.env`` file at startup by :mod:`kavara_enhancer.env`
2. the operating system keyring (optional: ``pip install "kavara-audio-enhancer[keyring]"``)
3. an interactive prompt (handled by the caller), which can offer to save to the keyring

The keyring helpers never raise: if the ``keyring`` package or a usable backend is
missing they simply report that nothing was found or saved.
"""

from __future__ import annotations

import os
from typing import Optional

KEYRING_SERVICE = "kavara-audio-enhancer"
KEYRING_USERNAME = "gemini-api-key"


def keyring_available() -> bool:
    """True if the optional ``keyring`` package can be imported."""
    try:
        import keyring  # noqa: F401
    except Exception:
        return False
    return True


def get_keyring_key() -> Optional[str]:
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME) or None
    except Exception:
        return None


def save_keyring_key(api_key: str) -> bool:
    """Store the key in the OS keyring. Returns False if no usable keyring exists."""
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, api_key)
        return True
    except Exception:
        return False


def delete_keyring_key() -> bool:
    """Remove the stored key. Returns False if there was none or no keyring is usable."""
    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        return True
    except Exception:
        return False


def find_api_key() -> tuple[Optional[str], str]:
    """Return ``(key, source)`` using the documented lookup order, or ``(None, "")``.

    A key found in the keyring is exported to ``GEMINI_API_KEY`` for this process so
    the Gemini client can pick it up.
    """
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        return env_key, "environment / .env"

    keyring_key = get_keyring_key()
    if keyring_key:
        os.environ["GEMINI_API_KEY"] = keyring_key
        return keyring_key, "system keyring"

    return None, ""
