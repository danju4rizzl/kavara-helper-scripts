"""Map timestamps from the original recording onto the edited (cut + sped-up) timeline."""

from __future__ import annotations

from .models import CutSegment, TimedWord


def remap_words(words: list[TimedWord], cuts: list[CutSegment], speed: float = 1.0) -> list[TimedWord]:
    """Re-time words for the final output; words inside removed cuts are dropped.

    ``cuts`` must be sanitized (sorted, non-overlapping), as produced by ``sanitize_cuts``.
    """
    speed = speed if speed > 0 else 1.0

    def removed_before(t: float) -> float:
        total = 0.0
        for cut in cuts:
            if cut.start_time >= t:
                break
            total += min(cut.end_time, t) - cut.start_time
        return total

    out: list[TimedWord] = []
    for word in words:
        midpoint = (word.start_time + word.end_time) / 2
        if any(cut.start_time <= midpoint < cut.end_time for cut in cuts):
            continue
        start = (word.start_time - removed_before(word.start_time)) / speed
        end = (word.end_time - removed_before(word.end_time)) / speed
        out.append(TimedWord(word.text, round(start, 3), round(max(end, start), 3)))
    return out
