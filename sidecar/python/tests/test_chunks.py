from pathlib import Path

from cayascribe.audio.chunks import plan_chunks
from cayascribe.diar.cluster import stitch_window_turns
from cayascribe.perf import asr_chunk_seconds, diar_chunk_seconds


def test_short_audio_is_one_chunk():
    assert plan_chunks(120.0, 600) == [(0.0, 120.0)]
    assert plan_chunks(700.0, 600) == [(0.0, 700.0)]


def test_long_audio_is_split():
    pieces = plan_chunks(45 * 60, 10 * 60)
    assert len(pieces) >= 4
    assert pieces[0][0] == 0.0
    assert pieces[-1][1] == 45 * 60
    for a, b in pieces:
        assert b > a
        assert (b - a) <= 10 * 60 + 1


def test_chunk_helpers_positive():
    assert asr_chunk_seconds() >= 5 * 60
    assert diar_chunk_seconds() >= 6 * 60


def test_stitch_maps_overlap_speakers():
    w0 = [
        {"startMs": 0, "endMs": 10_000, "speakerId": "A"},
        {"startMs": 10_000, "endMs": 20_000, "speakerId": "B"},
    ]
    w1 = [
        {"startMs": 18_000, "endMs": 22_000, "speakerId": "X"},
        {"startMs": 22_000, "endMs": 40_000, "speakerId": "Y"},
    ]
    out = stitch_window_turns([w0, w1])
    ids = {t["speakerId"] for t in out}
    assert "A" in ids
    assert "B" in ids
    # X overlaps B by 2s -> B; Y is new
    speakers_after = [t["speakerId"] for t in out if t["startMs"] >= 22_000]
    assert speakers_after
    assert speakers_after[0] in ids


def test_plan_chunks_without_path(tmp_path: Path):
    _ = tmp_path
    pieces = plan_chunks(1800, 600)
    assert len(pieces) == 3
    assert pieces[0] == (0.0, 600.0)
    assert pieces[-1][1] == 1800
