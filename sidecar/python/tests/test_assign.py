from cayascribe.diar.cluster import (
    assign_speakers,
    embedding_path,
    iter_diar_segments,
    speaker_letter,
)


class _FakeResult:
    def __init__(self, segs):
        self._segs = segs

    def sort_by_start_time(self):
        return self._segs


def test_iter_diar_sort_by_start_time():
    class Seg:
        def __init__(self, start, end, speaker):
            self.start = start
            self.end = end
            self.speaker = speaker

    segs = [Seg(0.0, 1.0, 0), Seg(1.2, 2.0, 1)]
    out = iter_diar_segments(_FakeResult(segs))
    assert len(out) == 2
    assert out[0].speaker == 0


def test_iter_diar_non_iterable_without_sorter():
    class Blob:
        pass

    assert iter_diar_segments(Blob()) == []


def test_iter_diar_already_list():
    segs = [object(), object()]
    assert iter_diar_segments(segs) is not segs
    assert iter_diar_segments(segs) == segs


def test_iter_diar_none():
    assert iter_diar_segments(None) == []


def test_embedding_prefers_wespeaker(tmp_path, monkeypatch):
    wes = tmp_path / "wespeaker.onnx"
    wes.write_bytes(b"w" * 8)
    tiny = tmp_path / "titanet.onnx"
    tiny.write_bytes(b"t" * 8)

    class Rec:
        def __init__(self, p):
            self._p = p

        def local_path(self):
            return self._p

    def fake_by_id(asset_id):
        if asset_id == "wespeaker-resnet293-lm":
            return Rec(wes)
        if asset_id == "titanet-small":
            return Rec(tiny)
        raise KeyError(asset_id)

    monkeypatch.setattr("cayascribe.diar.cluster.by_id", fake_by_id)
    assert embedding_path() == wes


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
