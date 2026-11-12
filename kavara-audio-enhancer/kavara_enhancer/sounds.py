"""Short audio cues so you can look away while a long job runs.

Each event has a distinct, recognisable pattern:
  start    - one short, mid-pitch blip            ("working on it")
  complete - three rising notes (C-E-G major)     ("done, success")
  error    - two low falling notes                ("something failed")

Windows uses winsound tones (no sound files needed). Elsewhere the terminal
bell is used (once for start/complete, twice for error). Sounds never raise,
stay silent when output is not a terminal, and can be disabled with
``--no-sound`` or ``KAVARA_SOUND=0``.
"""

from __future__ import annotations

import os
import sys

EVENT_START = "start"
EVENT_COMPLETE = "complete"
EVENT_ERROR = "error"

# (frequency Hz, duration ms) per event.
TONES: dict[str, list[tuple[int, int]]] = {
    EVENT_START: [(660, 120)],
    EVENT_COMPLETE: [(523, 130), (659, 130), (784, 260)],
    EVENT_ERROR: [(330, 220), (220, 380)],
}
BELL_COUNTS = {EVENT_START: 1, EVENT_COMPLETE: 1, EVENT_ERROR: 2}

_enabled = True


def set_enabled(enabled: bool) -> None:
    global _enabled
    _enabled = enabled


def is_enabled() -> bool:
    if not _enabled:
        return False
    if os.environ.get("KAVARA_SOUND", "").strip().lower() in ("0", "off", "false", "no"):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def play(event: str) -> None:
    """Play the cue for ``event``; silently does nothing if unavailable."""
    if event not in TONES or not is_enabled():
        return
    try:
        if sys.platform == "win32":
            import winsound

            for frequency, duration in TONES[event]:
                winsound.Beep(frequency, duration)
        else:
            sys.stdout.write("\a" * BELL_COUNTS[event])
            sys.stdout.flush()
    except Exception:
        pass
