import math

from kavara_enhancer.cutting import sanitize_cuts, total_cut_duration
from kavara_enhancer.models import CutSegment
from kavara_enhancer.ui import format_cut_report


def cuts(*pairs):
    return [CutSegment(a, b) for a, b in pairs]


def as_pairs(segments):
    return [(c.start_time, c.end_time) for c in segments]


def test_clamps_to_file_bounds():
    assert as_pairs(sanitize_cuts(cuts((-1.0, 0.5), (9.5, 12.0)), 10.0)) == [(0.0, 0.5), (9.5, 10.0)]


def test_drops_inverted_zero_length_and_tiny_cuts():
    result = sanitize_cuts(cuts((5, 4), (3, 3), (2.0, 2.01), (6, 7)), 10.0)
    assert as_pairs(result) == [(6, 7)]


def test_drops_cuts_entirely_beyond_the_end():
    assert sanitize_cuts(cuts((11, 12)), 10.0) == []


def test_drops_non_finite_timestamps():
    assert sanitize_cuts(cuts((math.nan, 2), (1, math.inf)), 10.0) == []


def test_merges_overlapping_touching_and_unsorted():
    result = sanitize_cuts(cuts((5, 6), (1, 2), (1.5, 3), (3, 3.5)), 10.0)
    assert as_pairs(result) == [(1, 3.5), (5, 6)]


def test_does_not_mutate_input():
    original = cuts((1, 2), (1.5, 3))
    sanitize_cuts(original, 10.0)
    assert as_pairs(original) == [(1, 2), (1.5, 3)]


def test_total_cut_duration():
    assert total_cut_duration(cuts((1, 2), (4, 4.5))) == 1.5


def test_cut_report_empty():
    assert format_cut_report([], 10.0) == "No cuts planned."


def test_cut_report_summary_and_speed():
    report = format_cut_report(cuts((1, 2), (4, 5)), 10.0, speed=2.0)
    assert "00:00:01.000 -> 00:00:02.000  (1.00s)" in report
    assert "2 cut(s) removing 2.0s of 10.0s (20.0%)." in report
    assert "Resulting duration: 00:04 (after 2.0x speed)." in report


def test_cut_report_truncates_long_lists():
    many = cuts(*[(i, i + 0.5) for i in range(0, 100, 2)])
    report = format_cut_report(many, 100.0, max_listed=5)
    assert "... and 45 more" in report
