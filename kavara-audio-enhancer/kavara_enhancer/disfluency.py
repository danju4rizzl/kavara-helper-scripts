"""Find filler words and repeated phrases in word-timed transcripts (pure, no I/O)."""

from __future__ import annotations

import re

from .constants import (
    FILLER_WORDS, MAX_REPEAT_GAP_SECONDS, MAX_REPEAT_PHRASE_WORDS,
)
from .models import CutSegment, TimedWord


def _normalize(text: str) -> str:
    return re.sub(r"[^\w']+", "", text.lower())


def find_filler_cuts(words: list[TimedWord]) -> list[CutSegment]:
    """Cut every standalone filler word ("um", "uh", ...)."""
    return [
        CutSegment(w.start_time, w.end_time)
        for w in words
        if _normalize(w.text) in FILLER_WORDS and w.end_time > w.start_time
    ]


def find_repeat_cuts(
    words: list[TimedWord],
    max_phrase_words: int = MAX_REPEAT_PHRASE_WORDS,
    max_gap: float = MAX_REPEAT_GAP_SECONDS,
) -> list[CutSegment]:
    """Delete the earlier take when a phrase is immediately restarted.

    "I just want to ... I just want to click here" -> cut the first "I just want to ...",
    keeping the final, complete take. Longest phrases are matched first, and a phrase
    said three times drops the first two. Fillers between the takes are ignored while
    matching (they get cut separately).
    """
    # Work on non-filler words only so "I just um I just" still counts as a repeat.
    kept = [w for w in words if _normalize(w.text) not in FILLER_WORDS and _normalize(w.text)]
    norm = [_normalize(w.text) for w in kept]
    cuts: list[CutSegment] = []

    i = 0
    while i < len(kept):
        matched = 0
        for n in range(min(max_phrase_words, (len(kept) - i) // 2), 0, -1):
            if norm[i:i + n] != norm[i + n:i + 2 * n]:
                continue
            if kept[i + n].start_time - kept[i + n - 1].end_time > max_gap:
                continue  # a long pause means a deliberate repeat, not a stumble
            matched = n
            break
        if matched:
            cuts.append(CutSegment(kept[i].start_time, kept[i + matched].start_time))
            i += matched  # re-check: the second take may itself be repeated
        else:
            i += 1
    return cuts


def find_disfluency_cuts(words: list[TimedWord]) -> list[CutSegment]:
    """All filler-word and repeated-phrase cuts (overlaps are merged later by sanitize_cuts)."""
    return find_filler_cuts(words) + find_repeat_cuts(words)
