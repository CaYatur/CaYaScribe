import subprocess
import sys
import threading
import time

from cayascribe.pipeline.ffmpeg import parse_hms
from cayascribe.pipeline.job_worker import main as worker_main
from cayascribe.pipeline.jobs import JobRunner, _overall, kill_popen_tree


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


def test_cancel_drops_late_done():
    runner = JobRunner()
    runner._events["abc123"] = []
    runner._cancel["abc123"] = threading.Event()
    runner._cancel["abc123"].set()
    runner._emit("abc123", "done", {"segments": [{"id": "s0000"}]})
    runner._emit("abc123", "cancelled", {"ok": True})
    names = [n for n, _ in runner.events("abc123")]
    assert "done" not in names
    assert "cancelled" in names


def test_kill_popen_tree_stops_child():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    try:
        assert proc.poll() is None
        kill_popen_tree(proc)
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)


def test_cancel_kills_attached_worker():
    runner = JobRunner()
    runner._current = "abc123"
    runner._events["abc123"] = []
    runner._cancel["abc123"] = threading.Event()
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    runner._procs["abc123"] = proc
    try:
        assert proc.poll() is None
        runner.cancel("abc123")
        deadline = time.time() + 5
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.05)
        assert proc.poll() is not None
        assert runner.busy() is False
        names = [n for n, _ in runner.events("abc123")]
        assert "cancelled" in names
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)


def test_parse_hms():
    assert parse_hms("00:01:23.50") == 83.5
    assert parse_hms("Duration: 00:00:09.04, start: 0.000000") == 9.04
    assert parse_hms("out_time=00:00:12.345000") == 12.345
    assert parse_hms("") is None


def test_overall_maps_stage_into_job_range():
    assert _overall(32, 99, 0) == 32
    assert _overall(32, 99, 100) == 99
    assert _overall(12, 32, 50) == 22


def test_worker_exits_when_cancel_file_exists(tmp_path):
    req = tmp_path / "request.json"
    events = tmp_path / "events.jsonl"
    req.write_text(
        '{"mediaPath": "C:/missing.wav", "language": "tr", "quality": "fast"}',
        encoding="utf-8",
    )
    (tmp_path / "CANCEL").write_text("1", encoding="utf-8")
    assert worker_main(["jid", str(req), str(events)]) == 0
    text = events.read_text(encoding="utf-8")
    assert "cancelled" in text
    assert "done" not in text
