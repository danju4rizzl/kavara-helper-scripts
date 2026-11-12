"""Find filler words and repeated phrases in word-timed transcripts (pure, no I/O)."""

from __future__ import annotations

import re

from .constants import (
    FILLER_PATTERN, MAX_REPEAT_GAP_SECONDS, MAX_REPEAT_PHRASE_WORDS,
    RESTART_MAX_GAP_SECONDS, RESTART_MAX_SPAN_SECONDS, RESTART_MAX_SPAN_WORDS,
    RESTART_MIN_OPENER_WORDS,
)
from .models import CutSegment, TimedWord


def _normalize(text: str) -> str:
    return re.sub(r"[^\w']+", "", text.lower())


_FILLER_RE = re.compile(FILLER_PATTERN)
_TRUNCATED_SUFFIXES = ("-", "–", "—")  # trailing dash: "wa-"


def is_filler(text: str) -> bool:
    """True for um/uh/hmm in any stretched spelling ("Uhmmmmm", "uhhh", "Ermm")."""
    return bool(_FILLER_RE.fullmatch(_normalize(text)))


def _is_truncated(text: str) -> bool:
    return text.strip().endswith(_TRUNCATED_SUFFIXES)


def find_filler_cuts(words: list[TimedWord]) -> list[CutSegment]:
    """Cut every filler word ("um", "uh", ...) and cut-off word fragments ("wa-")."""
    return [
        CutSegment(w.start_time, w.end_time)
        for w in words
        if (is_filler(w.text) or _is_truncated(w.text)) and w.end_time > w.start_time
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
    kept = [
        w for w in words
        if _normalize(w.text) and not is_filler(w.text) and not _is_truncated(w.text)
    ]
    norm = [_normalize(w.text) for w in kept]
    cuts: list[CutSegment] = []

    i = 0
    while i < len(kept):
        matched = 0
        for n in range(min(max_phrase_words, (len(kept) - i) // 2), 0, -1):
            first, second = norm[i:i + n], norm[i + n:i + 2 * n]
            # The first take may end mid-word ("I just wa" -> "I just want"): allow a prefix.
            if first[:-1] != second[:-1] or not second[-1].startswith(first[-1]):
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


def _ends_sentence(text: str) -> bool:
    return text.strip().endswith((".", "?", "!"))


def find_restart_cuts(
    words: list[TimedWord],
    min_opener: int = RESTART_MIN_OPENER_WORDS,
    max_span: int = RESTART_MAX_SPAN_WORDS,
    max_gap: float = RESTART_MAX_GAP_SECONDS,
    max_seconds: float = RESTART_MAX_SPAN_SECONDS,
) -> list[CutSegment]:
    """Drop an abandoned attempt when the speaker restarts the same sentence opening.

    "we're going to use another very popular ... we're going to use a very popular product"
    shares the opener "we're going to use", so the first, unfinished attempt is cut even
    though the rest differs. Needs a shared opener of ``min_opener`` words, and the abandoned
    attempt must be a single sentence (no full stop inside it) lasting under ``max_seconds``,
    so asides and separate sentences between similar lines are never deleted.
    """
    kept = [
        w for w in words
        if _normalize(w.text) and not is_filler(w.text) and not _is_truncated(w.text)
    ]
    norm = [_normalize(w.text) for w in kept]
    cuts: list[CutSegment] = []

    i = 0
    while i < len(kept) - min_opener:
        hit = 0
        for j in range(i + 2, min(i + max_span, len(kept) - 1) + 1):
            k = 0
            while j + k < len(kept) and norm[i + k] == norm[j + k] and i + k < j:
                k += 1
            if k < min_opener:
                continue
            unfinished = not any(_ends_sentence(w.text) for w in kept[i:j - 1])
            if not unfinished or kept[j].start_time - kept[i].start_time > max_seconds:
                continue
            if kept[j].start_time - kept[j - 1].end_time > max_gap:
                continue
            hit = j
            break
        if hit:
            cuts.append(CutSegment(kept[i].start_time, kept[hit].start_time))
            i = hit
        else:
            i += 1
    return cuts


def find_disfluency_cuts(words: list[TimedWord]) -> list[CutSegment]:
    """All filler, repeated-phrase and restart cuts (overlaps are merged later by sanitize_cuts)."""
    return find_filler_cuts(words) + find_repeat_cuts(words) + find_restart_cuts(words)
