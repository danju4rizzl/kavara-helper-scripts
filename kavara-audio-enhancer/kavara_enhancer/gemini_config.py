"""Gemini model selection and display labels.

The active model is resolved once at startup (``--model`` flag, then the
``GEMINI_MODEL`` environment variable / ``.env`` entry, then the built-in default)
and read from here everywhere, so the API calls and every on-screen label agree.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from .constants import DEFAULT_GEMINI_MODEL, GEMINI_MODEL_LABEL

_active_model: Optional[str] = None


def model_label_from_id(model_id: str) -> str:
    """Turn an API model id into a readable label.

    ``gemini-2.5-flash`` -> ``Gemini 2.5 Flash``; a leading ``models/`` is ignored.
    """
    name = model_id.strip().removeprefix("models/")
    tokens = [token for token in re.split(r"[-_\s]+", name) if token]
    if not tokens:
        return "Gemini"
    return " ".join(token if token[0].isdigit() else token.capitalize() for token in tokens)


def resolve_model(cli_value: Optional[str] = None) -> str:
    """Pick the model id: CLI flag, then ``GEMINI_MODEL`` env var, then the default."""
    for candidate in (cli_value, os.environ.get("GEMINI_MODEL")):
        if candidate and candidate.strip():
            return candidate.strip().removeprefix("models/")
    return DEFAULT_GEMINI_MODEL


def set_active_model(model_id: Optional[str]) -> str:
    """Set (or, with ``None``, reset) the model used for this run and return its id."""
    global _active_model
    _active_model = resolve_model(model_id) if model_id else None
    return active_model()


def active_model() -> str:
    """The model id to send to the API."""
    return _active_model or resolve_model(None)


def gemini_label() -> str:
    """Human-readable name of the active model for UI text."""
    model_id = active_model()
    if model_id == DEFAULT_GEMINI_MODEL:
        return GEMINI_MODEL_LABEL
    return model_label_from_id(model_id)
