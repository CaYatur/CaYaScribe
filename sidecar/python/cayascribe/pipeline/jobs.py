from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cayascribe.asr.engine import transcribe
from cayascribe.assets.manifest import quality_ready
from cayascribe.diar.cluster import assign_speakers, diarize
from cayascribe.models import JobCreate
from cayascribe.offline import assert_local_media
from cayascribe.paths import jobs_dir
from cayascribe.pipeline.ffmpeg import extract_wav

EmitFn = Callable[[str, dict[str, Any]], None]


def kill_popen_tree(proc: subprocess.Popen | None) -> None:
    """Kill a worker and every child (ffmpeg, CTranslate2 threads) immediately."""
    if proc is None:
        return
    pid = proc.pid
    if pid and os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    elif proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    text = raw.decode("utf-8", errors="replace")
    if not text.endswith("\n") and "\n" in text:
        text = text.rsplit("\n", 1)[0]
    elif not text.endswith("\n"):
        return []
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and "event" in rec:
            out.append(rec)
    return out


def _cleanup_wavs(work: Path) -> None:
    try:
        for p in work.glob("*.wav"):
            try:
                p.unlink()
            except OSError:
                pass
    except OSError:
        pass


def _overall(lo: int, hi: int, stage_pct: int) -> int:
    stage_pct = max(0, min(100, int(stage_pct)))
    return lo + int((hi - lo) * stage_pct / 100)


def run_job_body(
    job_id: str,
    req: JobCreate,
    emit: EmitFn,
    cancel: threading.Event,
) -> None:
    work = jobs_dir() / job_id
    work.mkdir(parents=True, exist_ok=True)
    try:
        if cancel.is_set():
            raise RuntimeError("cancelled")
        if not quality_ready(req.quality, req.asrId):
            raise RuntimeError("models_missing_for_quality")
        media = assert_local_media(req.mediaPath)
        speaker_count = req.speakerCount
        do_diar = speaker_count != 1
        extract_span = (1, 12)
        diar_span = (12, 32)
        asr_span = (32, 99) if do_diar else (12, 99)

        def push_progress(
            stage: str,
            stage_pct: int,
            *,
            done: int | None = None,
            total: int | None = None,
        ) -> None:
            lo, hi = {"extract": extract_span, "diarize": diar_span, "asr": asr_span}[stage]
            payload: dict[str, Any] = {
                "stage": stage,
                "pct": _overall(lo, hi, stage_pct),
                "stagePct": max(0, min(100, int(stage_pct))),
            }
            if done is not None:
                payload["stageDone"] = int(done)
            if total is not None:
                payload["stageTotal"] = int(total)
            emit("progress", payload)

        push_progress("extract", 0)
        wav = extract_wav(
            media,
            work / "original_16k.wav",
            16000,
            cancel=cancel,
            on_progress=lambda pct, _elapsed, _dur: push_progress("extract", pct),
        )
        push_progress("extract", 100)
        if cancel.is_set():
            raise RuntimeError("cancelled")

        turns: list[dict[str, Any]] = []
        diar_name = "none"
        if do_diar:
            push_progress("diarize", 0)
            if cancel.is_set():
                raise RuntimeError("cancelled")
            try:
                turns = diarize(
                    wav,
                    speaker_count,
                    cancel=cancel,
                    embed_id=req.embedId,
                    on_progress=lambda done, total: push_progress(
                        "diarize",
                        int(100 * done / max(total, 1)),
                        done=done,
                        total=total,
                    ),
                )
                diar_name = "sherpa-onnx" if turns else "skipped"
            except Exception:
                if cancel.is_set():
                    raise RuntimeError("cancelled") from None
                turns = []
                diar_name = "skipped"
            push_progress("diarize", 100)

        if cancel.is_set():
            raise RuntimeError("cancelled")
        push_progress("asr", 0)
        segments: list[dict[str, Any]] = []
        engine = "whisper"
        language = req.language
        for item in transcribe(
            wav,
            req.quality,
            req.language,
            turns=turns,
            cancel=cancel,
            asr_id=req.asrId,
        ):
            if cancel.is_set():
                raise RuntimeError("cancelled")
            if item["type"] == "meta":
                engine = item["engine"]
                language = item["language"]
                emit("meta", item)
                continue
            if item["type"] == "progress":
                stage_pct = item.get("stagePct")
                if stage_pct is None and item.get("pct") is not None:
                    stage_pct = max(0, min(100, int((int(item["pct"]) - 35) * 100 / 65)))
                push_progress(
                    str(item.get("stage") or "asr"),
                    int(stage_pct or 0),
                    done=int(item["stageDone"]) if item.get("stageDone") is not None else None,
                    total=int(item["stageTotal"]) if item.get("stageTotal") is not None else None,
                )
                continue
            segments.append(
                {
                    "id": item["id"],
                    "speakerId": "A",
                    "startMs": item["startMs"],
                    "endMs": item["endMs"],
                    "text": item["text"],
                }
            )
            emit("segment_raw", item)

        push_progress("asr", 100)
        if cancel.is_set():
            raise RuntimeError("cancelled")

        if speaker_count == 1 or not turns:
            for s in segments:
                s["speakerId"] = "A"
            if speaker_count == 1:
                diar_name = "single"
        else:
            assign_speakers(segments, turns)

        speaker_ids = []
        for s in segments:
            if s["speakerId"] not in speaker_ids:
                speaker_ids.append(s["speakerId"])
        if not speaker_ids:
            speaker_ids = ["A"]
        speakers = [{"id": sid, "name": sid} for sid in speaker_ids]

        result = {
            "jobId": job_id,
            "language": language,
            "engine": engine,
            "diarization": diar_name,
            "segments": segments,
            "speakers": speakers,
        }
        (work / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if cancel.is_set():
            raise RuntimeError("cancelled")
        emit("done", result)
    except MemoryError:
        emit("error", {"error": "out_of_memory"})
    except Exception as exc:
        cancelled = cancel.is_set() or str(exc) == "cancelled"
        if cancelled:
            emit("cancelled", {"ok": True})
        else:
            msg = str(exc)
            low = msg.lower()
            if "memory" in low or "std::bad_alloc" in low:
                msg = "out_of_memory"
            emit("error", {"error": msg})
    finally:
        _cleanup_wavs(work)


class JobRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: str | None = None
        self._events: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._procs: dict[str, subprocess.Popen] = {}
        self._worker: subprocess.Popen | None = None
        self._worker_log: Any = None
        self._worker_lock = threading.Lock()

    def busy(self) -> bool:
        with self._lock:
            return self._current is not None

    def start(self, req: JobCreate) -> str:
        if not quality_ready(req.quality, req.asrId):
            raise RuntimeError("models_missing_for_quality")
        with self._lock:
            if self._current:
                raise RuntimeError("job_running")
            job_id = uuid.uuid4().hex[:12]
            self._current = job_id
            self._events[job_id] = []
            self._cancel[job_id] = threading.Event()
        (jobs_dir() / job_id).mkdir(parents=True, exist_ok=True)
        t = threading.Thread(target=self._spawn_and_pump, args=(job_id, req), daemon=True)
        t.start()
        return job_id

    def cancel(self, job_id: str) -> None:
        ev = self._cancel.get(job_id)
        if ev:
            ev.set()
        try:
            (jobs_dir() / job_id / "CANCEL").write_text("1", encoding="utf-8")
        except OSError:
            pass
        proc = self._procs.pop(job_id, None)
        with self._worker_lock:
            if proc is not None and self._worker is proc:
                self._worker = None
        kill_popen_tree(proc)
        with self._lock:
            if self._current == job_id:
                self._current = None
        events = self._events.get(job_id) or []
        if not any(name == "cancelled" for name, _ in events):
            self._emit(job_id, "cancelled", {"ok": True})

    def _ensure_worker(self) -> subprocess.Popen:
        with self._worker_lock:
            if self._worker is not None and self._worker.poll() is None:
                return self._worker
            root = jobs_dir()
            root.mkdir(parents=True, exist_ok=True)
            if self._worker_log is None:
                self._worker_log = open(root / "worker.log", "a", encoding="utf-8")  # noqa: SIM115
            popen_kw: dict[str, Any] = {
                "stdin": subprocess.PIPE,
                "stdout": self._worker_log,
                "stderr": self._worker_log,
                "text": True,
                "encoding": "utf-8",
                "bufsize": 1,
            }
            if os.name == "nt":
                popen_kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._worker = subprocess.Popen(
                [sys.executable, "-m", "cayascribe.pipeline.job_worker", "--serve"],
                **popen_kw,
            )
            return self._worker

    def events(self, job_id: str) -> list[tuple[str, dict[str, Any]]]:
        return list(self._events.get(job_id, []))

    def result(self, job_id: str) -> dict[str, Any] | None:
        return self._results.get(job_id)

    def _emit(self, job_id: str, event: str, data: dict[str, Any]) -> None:
        with self._lock:
            cancelled = job_id in self._cancel and self._cancel[job_id].is_set()
            if cancelled and event == "done":
                return
            self._events.setdefault(job_id, []).append((event, data))

    def _spawn_and_pump(self, job_id: str, req: JobCreate) -> None:
        work = jobs_dir() / job_id
        work.mkdir(parents=True, exist_ok=True)
        req_path = work / "request.json"
        events_path = work / "events.jsonl"
        req_path.write_text(req.model_dump_json(), encoding="utf-8")
        proc: subprocess.Popen | None = None
        try:
            proc = self._ensure_worker()
            self._procs[job_id] = proc
            payload = json.dumps(
                {
                    "jobId": job_id,
                    "requestPath": str(req_path),
                    "eventsPath": str(events_path),
                }
            )
            if proc.stdin is None:
                raise RuntimeError("worker_stdin_missing")
            try:
                proc.stdin.write(payload + "\n")
                proc.stdin.flush()
            except BrokenPipeError:
                with self._worker_lock:
                    self._worker = None
                proc = self._ensure_worker()
                self._procs[job_id] = proc
                if proc.stdin is None:
                    raise RuntimeError("worker_stdin_missing") from None
                proc.stdin.write(payload + "\n")
                proc.stdin.flush()
            self._pump(job_id, events_path, proc)
        except Exception as exc:
            if self._cancel.get(job_id) is not None and self._cancel[job_id].is_set():
                if not any(name == "cancelled" for name, _ in (self._events.get(job_id) or [])):
                    self._emit(job_id, "cancelled", {"ok": True})
            else:
                self._emit(job_id, "error", {"error": str(exc)})
        finally:
            self._procs.pop(job_id, None)
            cancelled = self._cancel.get(job_id) is not None and self._cancel[job_id].is_set()
            if cancelled:
                with self._worker_lock:
                    w = self._worker
                    self._worker = None
                if w is not None:
                    kill_popen_tree(w)
            _cleanup_wavs(work)
            with self._lock:
                if self._current == job_id:
                    self._current = None

    def _pump(self, job_id: str, events_path: Path, proc: subprocess.Popen) -> None:
        idx = 0
        terminal = False
        while True:
            rows = _read_jsonl(events_path)
            while idx < len(rows):
                rec = rows[idx]
                idx += 1
                ev = str(rec.get("event") or "")
                data = rec.get("data") if isinstance(rec.get("data"), dict) else {}
                if ev == "done":
                    self._results[job_id] = data
                self._emit(job_id, ev, data)
                if ev in ("done", "error", "cancelled"):
                    terminal = True
                    break
            if terminal:
                return
            if proc.poll() is not None:
                rows = _read_jsonl(events_path)
                while idx < len(rows):
                    rec = rows[idx]
                    idx += 1
                    ev = str(rec.get("event") or "")
                    data = rec.get("data") if isinstance(rec.get("data"), dict) else {}
                    if ev == "done":
                        self._results[job_id] = data
                    self._emit(job_id, ev, data)
                    if ev in ("done", "error", "cancelled"):
                        return
                cancelled = self._cancel.get(job_id) is not None and self._cancel[job_id].is_set()
                events = self._events.get(job_id) or []
                if cancelled:
                    if not any(name == "cancelled" for name, _ in events):
                        self._emit(job_id, "cancelled", {"ok": True})
                elif not any(name in ("done", "error", "cancelled") for name, _ in events):
                    code = proc.returncode
                    self._emit(job_id, "error", {"error": f"worker_exited:{code}"})
                return
            time.sleep(0.12)


RUNNER = JobRunner()


def _shutdown_runner() -> None:
    jid = RUNNER._current
    if jid:
        RUNNER.cancel(jid)
    with RUNNER._worker_lock:
        w = RUNNER._worker
        RUNNER._worker = None
    if w is not None:
        kill_popen_tree(w)


atexit.register(_shutdown_runner)
