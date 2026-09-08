from __future__ import annotations

import queue
import re
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from cayascribe.assets.manifest import ffmpeg_exe

_HMS = re.compile(r"(-?\d+):(\d+):(\d+(?:\.\d+)?)")


class FfmpegError(RuntimeError):
    pass


def parse_hms(text: str) -> float | None:
    match = _HMS.search((text or "").strip())
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _bin() -> Path:
    exe = ffmpeg_exe()
    if not exe:
        raise FfmpegError("ffmpeg_missing")
    return exe


def extract_wav(
    media: Path,
    dest: Path,
    sample_rate: int = 16000,
    cancel: threading.Event | None = None,
    on_proc=None,
    on_progress: Callable[[int, float, float], None] | None = None,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(_bin()),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "info",
        "-progress",
        "pipe:1",
        "-nostats",
        "-threads",
        "0",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(media),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        "-y",
        str(dest),
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    if on_proc is not None:
        on_proc(proc)
    err_text: list[str] = []
    duration_s = [0.0]
    lines: queue.Queue[str | None] = queue.Queue()

    def _stderr() -> None:
        if proc.stderr is None:
            return
        for raw in proc.stderr:
            err_text.append(raw)
            if duration_s[0] <= 0 and "Duration:" in raw:
                found = parse_hms(raw.split("Duration:", 1)[-1])
                if found and found > 0:
                    duration_s[0] = found

    def _stdout() -> None:
        if proc.stdout is None:
            lines.put(None)
            return
        for raw in proc.stdout:
            lines.put(raw)
        lines.put(None)

    threading.Thread(target=_stderr, daemon=True).start()
    threading.Thread(target=_stdout, daemon=True).start()
    last_pct = -1
    try:
        while True:
            if cancel is not None and cancel.is_set():
                _kill(proc)
                raise RuntimeError("cancelled")
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue
            if line is None:
                break
            stripped = line.strip()
            elapsed = None
            if stripped.startswith("out_time="):
                elapsed = parse_hms(stripped.split("=", 1)[-1])
            if elapsed is not None and duration_s[0] > 0 and on_progress is not None:
                pct = min(100, int(100 * elapsed / duration_s[0]))
                if pct != last_pct:
                    last_pct = pct
                    on_progress(pct, elapsed, duration_s[0])
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _kill(proc)
        stderr = "".join(err_text)
        if proc.returncode != 0 or not dest.is_file():
            raise FfmpegError((stderr or "").strip() or "ffmpeg_failed")
        if on_progress is not None:
            on_progress(100, duration_s[0], duration_s[0] or 1.0)
        return dest
    finally:
        if proc.poll() is None:
            _kill(proc)


def _kill(proc: subprocess.Popen) -> None:
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass


def license_ok() -> bool:
    exe = ffmpeg_exe()
    if not exe:
        return False
    proc = subprocess.run([str(exe), "-version"], capture_output=True, text=True, check=False)
    text = (proc.stdout or "") + (proc.stderr or "")
    if "--enable-gpl" in text or "libx264" in text:
        return False
    return proc.returncode == 0
