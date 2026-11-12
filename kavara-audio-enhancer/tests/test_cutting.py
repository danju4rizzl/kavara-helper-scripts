import pytest

from kavara_enhancer.cutting import generate_cut_filter, invert_segments
from kavara_enhancer.models import CutSegment


def cuts(*pairs):
    return [CutSegment(a, b) for a, b in pairs]


def test_no_cuts_keeps_everything():
    assert invert_segments([], 10.0) == [(0.0, 10.0)]


def test_simple_cut_in_middle():
    assert invert_segments(cuts((2, 3)), 10.0) == [(0.0, 2), (3, 10.0)]


def test_cut_at_start_and_end():
    assert invert_segments(cuts((0, 1), (9, 10)), 10.0) == [(1, 9)]


def test_unsorted_cuts_are_sorted():
    assert invert_segments(cuts((6, 7), (2, 3)), 10.0) == [(0.0, 2), (3, 6), (7, 10.0)]


def test_overlapping_and_touching_cuts_merge():
    assert invert_segments(cuts((2, 4), (3, 5), (5, 6)), 10.0) == [(0.0, 2), (6, 10.0)]


def test_nested_cut_is_absorbed():
    assert invert_segments(cuts((2, 8), (3, 4)), 10.0) == [(0.0, 2), (8, 10.0)]


def test_cutting_everything_leaves_nothing():
    assert invert_segments(cuts((0, 10)), 10.0) == []


def test_filter_raises_when_nothing_to_keep():
    with pytest.raises(ValueError):
        generate_cut_filter(cuts((0, 10)), 10.0)


def test_audio_only_filter_adds_declick_fades_at_joins():
    graph = generate_cut_filter(cuts((2, 3)), 10.0, video_stream=False, audio_stream=True)
    assert graph == (
        "[0:a]atrim=start=0.000:end=2.000,asetpts=PTS-STARTPTS,afade=t=out:st=1.990:d=0.010[a0];"
        "[0:a]atrim=start=3.000:end=10.000,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.010[a1];"
        "[a0][a1]concat=n=2:v=0:a=1[outa]"
    )


def test_middle_segments_fade_both_edges_and_outer_edges_stay_untouched():
    graph = generate_cut_filter(cuts((1, 2), (4, 5)), 10.0, audio_stream=True)
    first, middle, last = graph.split(";")[:3]
    assert "afade=t=in" not in first and "afade=t=out" in first
    assert "afade=t=in" in middle and "afade=t=out" in middle
    assert "afade=t=in" in last and "afade=t=out" not in last


def test_fade_never_exceeds_half_of_a_short_segment():
    graph = generate_cut_filter(cuts((1.0, 1.5)), 1.52, audio_stream=True)  # last keep is 0.02s long
    assert "afade=t=in:st=0:d=0.010" in graph
    graph = generate_cut_filter(cuts((0.5, 1.0)), 10.0, audio_stream=True, audio_fade=0.5)
    assert "d=0.250" in graph  # 0.5s keep -> fade capped at 0.25s


def test_audio_fade_can_be_disabled():
    graph = generate_cut_filter(cuts((2, 3)), 10.0, video_stream=False, audio_stream=True, audio_fade=0)
    assert graph == (
        "[0:a]atrim=start=0.000:end=2.000,asetpts=PTS-STARTPTS[a0];"
        "[0:a]atrim=start=3.000:end=10.000,asetpts=PTS-STARTPTS[a1];"
        "[a0][a1]concat=n=2:v=0:a=1[outa]"
    )


def test_video_only_filter_applies_speed():
    graph = generate_cut_filter(cuts((2, 3)), 10.0, video_stream=True, audio_stream=False, speed_factor=2.0)
    assert "concat=n=2:v=1:a=0[cutv];" in graph
    assert graph.endswith("[cutv]setpts=0.5000*PTS[outv]")


def test_video_only_filter_without_speed_has_no_setpts_scaling():
    graph = generate_cut_filter(cuts((2, 3)), 10.0, video_stream=True, audio_stream=False)
    assert graph.endswith("concat=n=2:v=1:a=0[outv]")


def test_audio_and_video_filter_concats_both():
    graph = generate_cut_filter(cuts((2, 3)), 10.0, video_stream=True, audio_stream=True)
    assert graph.endswith("[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]")
