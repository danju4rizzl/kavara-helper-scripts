"""Sound cues: right pattern per event, and never noisy when disabled."""

import sys
import types

import pytest

from kavara_enhancer import sounds


@pytest.fixture
def beeps(monkeypatch):
    played = []
    fake = types.SimpleNamespace(Beep=lambda f, d: played.append((f, d)))
    monkeypatch.setitem(sys.modules, "winsound", fake)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sounds, "is_enabled", lambda: True)
    return played


def test_events_have_distinct_patterns():
    patterns = [tuple(sounds.TONES[e]) for e in (sounds.EVENT_START, sounds.EVENT_COMPLETE, sounds.EVENT_ERROR)]
    assert len(set(patterns)) == 3


def test_complete_rises_and_error_falls():
    rising = [f for f, _ in sounds.TONES[sounds.EVENT_COMPLETE]]
    falling = [f for f, _ in sounds.TONES[sounds.EVENT_ERROR]]
    assert rising == sorted(rising)
    assert falling == sorted(falling, reverse=True)


def test_play_uses_the_events_tones(beeps):
    sounds.play(sounds.EVENT_COMPLETE)
    assert beeps == sounds.TONES[sounds.EVENT_COMPLETE]


def test_unknown_event_is_ignored(beeps):
    sounds.play("nope")
    assert beeps == []


def test_disabled_flag_and_env_silence_everything(monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    sounds.set_enabled(False)
    try:
        assert not sounds.is_enabled()
    finally:
        sounds.set_enabled(True)
    monkeypatch.setenv("KAVARA_SOUND", "0")
    assert not sounds.is_enabled()


def test_not_a_terminal_is_silent(monkeypatch):
    monkeypatch.delenv("KAVARA_SOUND", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False, raising=False)
    assert not sounds.is_enabled()


def test_play_never_raises(monkeypatch):
    monkeypatch.setattr(sounds, "is_enabled", lambda: True)
    fake = types.SimpleNamespace(Beep=lambda f, d: (_ for _ in ()).throw(RuntimeError("no device")))
    monkeypatch.setitem(sys.modules, "winsound", fake)
    monkeypatch.setattr(sys, "platform", "win32")
    sounds.play(sounds.EVENT_ERROR)
