import threading

from cayascribe.pipeline.jobs import JobRunner


def test_cancel_emits_and_clears_busy():
    runner = JobRunner()
    runner._current = "abc123"
    runner._events["abc123"] = []
    runner._cancel["abc123"] = threading.Event()
    runner.cancel("abc123")
    assert runner._cancel["abc123"].is_set()
    assert runner.busy() is False
    names = [n for n, _ in runner.events("abc123")]
    assert "cancelled" in names


def test_cancel_unknown_job_is_noop():
    runner = JobRunner()
    runner.cancel("missing")
    assert runner.busy() is False
