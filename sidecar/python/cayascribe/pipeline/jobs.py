from __future__ import annotations

import json
import subprocess
import threading
import uuid
from typing import Any

from cayascribe.asr.engine import transcribe
from cayascribe.assets.manifest import quality_ready
from cayascribe.diar.cluster import assign_speakers, diarize
from cayascribe.models import JobCreate
from cayascribe.offline import assert_local_media
from cayascribe.paths import jobs_dir
from cayascribe.pipeline.ffmpeg import extract_wav


class JobRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: str | None = None
        self._events: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._ffmpeg: dict[str, subprocess.Popen] = {}

    def busy(self) -> bool:
        with self._lock:
            return self._current is not None

    def start(self, req: JobCreate) -> str:
        if not quality_ready(req.quality):
            raise RuntimeError("models_missing_for_quality")
        with self._lock:
            if self._current:
                raise RuntimeError("job_running")
            job_id = uuid.uuid4().hex[:12]
            self._current = job_id
            self._events[job_id] = []
            self._cancel[job_id] = threading.Event()
        t = threading.Thread(target=self._run, args=(job_id, req), daemon=True)
        t.start()
        return job_id

    def cancel(self, job_id: str) -> None:
        ev = self._cancel.get(job_id)
        if ev:
            ev.set()
        proc = self._ffmpeg.pop(job_id, None)
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        with self._lock:
            if self._current == job_id:
                self._current = None
        events = self._events.get(job_id) or []
        if not any(name == "cancelled" for name, _ in events):
            self._emit(job_id, "cancelled", {"ok": True})

    def events(self, job_id: str) -> list[tuple[str, dict[str, Any]]]:
        return list(self._events.get(job_id, []))

    def result(self, job_id: str) -> dict[str, Any] | None:
        return self._results.get(job_id)

    def _emit(self, job_id: str, event: str, data: dict[str, Any]) -> None:
        self._events.setdefault(job_id, []).append((event, data))

    def _run(self, job_id: str, req: JobCreate) -> None:
        work = jobs_dir() / job_id
        work.mkdir(parents=True, exist_ok=True)
        try:
            if not quality_ready(req.quality):
                raise RuntimeError("models_missing_for_quality")
            media = assert_local_media(req.mediaPath)
            self._emit(job_id, "progress", {"stage": "extract", "pct": 5})
            wav = extract_wav(
                media,
                work / "original_16k.wav",
                16000,
                cancel=self._cancel[job_id],
                on_proc=lambda p: self._ffmpeg.__setitem__(job_id, p),
            )
            self._ffmpeg.pop(job_id, None)
            if self._cancel[job_id].is_set():
                raise RuntimeError("cancelled")

            speaker_count = req.speakerCount
            do_diar = speaker_count != 1
            turns: list[dict[str, Any]] = []
            diar_name = "none"
            if do_diar:
                self._emit(job_id, "progress", {"stage": "diarize", "pct": 20})
                if self._cancel[job_id].is_set():
                    raise RuntimeError("cancelled")
                try:
                    turns = diarize(wav, speaker_count)
                    diar_name = "sherpa-onnx" if turns else "skipped"
                except Exception:
                    if self._cancel[job_id].is_set():
                        raise RuntimeError("cancelled")
                    turns = []
                    diar_name = "skipped"

            if self._cancel[job_id].is_set():
                raise RuntimeError("cancelled")
            self._emit(job_id, "progress", {"stage": "asr", "pct": 35})
            segments: list[dict[str, Any]] = []
            engine = "whisper"
            language = req.language
            for item in transcribe(
                wav,
                req.quality,
                req.language,
                turns=turns,
                cancel=self._cancel[job_id],
            ):
                if self._cancel[job_id].is_set():
                    raise RuntimeError("cancelled")
                if item["type"] == "meta":
                    engine = item["engine"]
                    language = item["language"]
                    self._emit(job_id, "meta", item)
                    continue
                if item["type"] == "progress":
                    self._emit(
                        job_id,
                        "progress",
                        {"stage": str(item.get("stage") or "asr"), "pct": int(item.get("pct") or 35)},
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
                self._emit(job_id, "segment_raw", item)

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
            self._results[job_id] = result
            self._emit(job_id, "done", result)
        except Exception as exc:
            cancelled = self._cancel.get(job_id) is not None and self._cancel[job_id].is_set()
            if cancelled or str(exc) == "cancelled":
                events = self._events.get(job_id) or []
                if not any(name == "cancelled" for name, _ in events):
                    self._emit(job_id, "cancelled", {"ok": True})
            else:
                self._emit(job_id, "error", {"error": str(exc)})
        finally:
            proc = self._ffmpeg.pop(job_id, None)
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass
            for p in work.glob("*.wav"):
                try:
                    p.unlink()
                except OSError:
                    pass
            with self._lock:
                if self._current == job_id:
                    self._current = None


RUNNER = JobRunner()
