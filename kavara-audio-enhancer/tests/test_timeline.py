"""Re-timing a transcript of the original audio onto the edited timeline."""

from kavara_enhancer.models import CutSegment, TimedWord
from kavara_enhancer.timeline import remap_words


def w(text, a, b):
    return TimedWord(text, a, b)


def as_tuples(words):
    return [(x.text, x.start_time, x.end_time) for x in words]


def test_no_cuts_no_speed_is_identity():
    ws = [w("a", 1.0, 1.5), w("b", 2.0, 2.5)]
    assert as_tuples(remap_words(ws, [], 1.0)) == as_tuples(ws)


def test_words_after_a_cut_shift_earlier():
    ws = [w("a", 1.0, 1.5), w("b", 6.0, 6.5)]
    out = remap_words(ws, [CutSegment(2.0, 5.0)])
    assert as_tuples(out) == [("a", 1.0, 1.5), ("b", 3.0, 3.5)]


def test_words_inside_a_cut_are_dropped():
    ws = [w("so", 0.0, 0.3), w("um", 1.5, 2.0), w("yes", 3.0, 3.3)]
    out = remap_words(ws, [CutSegment(1.4, 2.1)])
    assert [x.text for x in out] == ["so", "yes"]
    assert out[1].start_time == round(3.0 - 0.7, 3)


def test_speed_scales_after_cuts():
    ws = [w("a", 4.0, 5.0)]
    (out,) = remap_words(ws, [CutSegment(0.0, 2.0)], speed=2.0)
    assert (out.start_time, out.end_time) == (1.0, 1.5)  # (4-2)/2, (5-2)/2
