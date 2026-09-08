from cayascribe.diar.cluster import assign_speakers, speaker_letter


def test_letters():
    assert speaker_letter(0) == "A"
    assert speaker_letter(1) == "B"


def test_assign_overlap():
    segs = [
        {"id": "s0", "speakerId": "A", "startMs": 0, "endMs": 1000, "text": "merhaba"},
        {"id": "s1", "speakerId": "A", "startMs": 1200, "endMs": 2000, "text": "alo"},
    ]
    turns = [
        {"startMs": 0, "endMs": 1100, "speakerId": "A"},
        {"startMs": 1100, "endMs": 2500, "speakerId": "B"},
    ]
    out = assign_speakers(segs, turns)
    assert out[0]["speakerId"] == "A"
    assert out[1]["speakerId"] == "B"


def test_no_turns_all_a():
    segs = [{"id": "s0", "speakerId": "X", "startMs": 0, "endMs": 10, "text": "x"}]
    out = assign_speakers(segs, [])
    assert out[0]["speakerId"] == "A"
