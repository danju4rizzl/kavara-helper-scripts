"""Filler/repeat detection and word-timed subtitle building (no network)."""

from types import SimpleNamespace as NS

from kavara_enhancer.ai import build_subtitles_from_words, extract_words
from kavara_enhancer.disfluency import find_disfluency_cuts, find_repeat_cuts
from kavara_enhancer.models import TimedWord


def words(text: str, step: float = 0.3, start: float = 0.0) -> list[TimedWord]:
    out, t = [], start
    for w in text.split():
        out.append(TimedWord(w, round(t, 3), round(t + step - 0.05, 3)))
        t += step
    return out


def test_restarted_phrase_drops_first_take():
    ws = words("I just want to I just want to click here")
    (cut,) = find_repeat_cuts(ws)
    assert cut.start_time == ws[0].start_time
    assert cut.end_time == ws[4].start_time  # second "I" survives


def test_fillers_cut_and_do_not_hide_repeats():
    ws = words("so I just um I just click")
    cuts = find_disfluency_cuts(ws)
    texts_cut = [c for c in cuts]
    assert any(c.start_time == ws[3].start_time for c in texts_cut)  # the "um"
    assert any(c.start_time == ws[1].start_time for c in texts_cut)  # first "I just"


def test_triple_repeat_keeps_only_last():
    ws = words("go to go to go to the store")
    cuts = find_repeat_cuts(ws)
    assert cuts[0].start_time == 0.0
    assert cuts[-1].end_time == ws[4].start_time


def test_long_pause_between_repeats_is_kept():
    a = words("no no")
    a[1] = TimedWord("no", 5.0, 5.3)
    assert find_repeat_cuts(a) == []


def test_no_false_positives():
    assert find_disfluency_cuts(words("this is a normal sentence")) == []


def test_extract_words_parses_offsets_and_shifts():
    info = lambda w, s, e: NS(word=w, start_offset=s, end_offset=e)
    resp = NS(candidates=[NS(content=NS(parts=[NS(audio_transcription=NS(words=[
        info("Hello", "0.5s", "0.9s"), info("late", "999s", "1000s"), info("", "1s", "2s"),
    ]))]))])
    got = extract_words(resp, offset_seconds=180.0, duration_seconds=180.0)
    assert [(w.text, w.start_time, w.end_time) for w in got] == [("Hello", 180.5, 180.9)]


def test_subtitles_break_on_sentence_and_gap():
    ws = words("Hello there friend. Next line starts here")
    ws[3:] = [TimedWord(w.text, w.start_time + 2, w.end_time + 2) for w in ws[3:]]
    subs = build_subtitles_from_words(ws)
    assert [s.text for s in subs] == ["Hello there friend.", "Next line starts here"]
    assert [s.index for s in subs] == [1, 2]
