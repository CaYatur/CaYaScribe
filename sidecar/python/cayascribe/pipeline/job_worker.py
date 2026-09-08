"""Isolated job process so Cancel can kill ASR/diarization immediately.

`--serve` keeps the process alive and caches models between jobs.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any


def _watch_cancel(path: Path, ev: threading.Event) -> None:
    while not ev.is_set():
        if path.is_file():
            ev.set()
            return
        time.sleep(0.08)


def run_listed(job_id: str, req_path: Path, events_path: Path) -> int:
    cancel = threading.Event()
    watch = threading.Thread(
        target=_watch_cancel,
        args=(req_path.parent / "CANCEL", cancel),
        daemon=True,
    )
    watch.start()
    lock = threading.Lock()
    emitted_terminal = False

    def emit(event: str, data: dict[str, Any]) -> None:
        nonlocal emitted_terminal
        with lock:
            if emitted_terminal:
                return
            if cancel.is_set() and event == "done":
                event = "cancelled"
                data = {"ok": True}
            events_path.parent.mkdir(parents=True, exist_ok=True)
            with events_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"event": event, "data": data}, ensure_ascii=False) + "\n")
                f.flush()
            if event in ("done", "error", "cancelled"):
                emitted_terminal = True

    if (req_path.parent / "CANCEL").is_file():
        cancel.set()
        emit("cancelled", {"ok": True})
        return 0

    from cayascribe.models import JobCreate
    from cayascribe.pipeline.jobs import run_job_body

    req = JobCreate.model_validate_json(req_path.read_text(encoding="utf-8"))
    run_job_body(job_id, req, emit, cancel)
    return 0


def serve() -> int:
    if os.name != "nt":
        try:
            os.setsid()
        except OSError:
            pass
    from cayascribe.perf import configure_threads

    configure_threads()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        if line == "shutdown":
            return 0
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        job_id = str(msg.get("jobId") or "")
        req_path = Path(str(msg.get("requestPath") or ""))
        events_path = Path(str(msg.get("eventsPath") or ""))
        if not job_id or not req_path or not events_path:
            continue
        run_listed(job_id, req_path, events_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "--serve":
        return serve()
    if len(args) != 3:
        print(
            "usage: python -m cayascribe.pipeline.job_worker JOB_ID REQUEST.json EVENTS.jsonl",
            file=sys.stderr,
        )
        print("   or: python -m cayascribe.pipeline.job_worker --serve", file=sys.stderr)
        return 2
    if os.name != "nt":
        try:
            os.setsid()
        except OSError:
            pass
    job_id, req_path_s, events_path_s = args
    return run_listed(job_id, Path(req_path_s), Path(events_path_s))


if __name__ == "__main__":
    raise SystemExit(main())
