from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from cayascribe.assets.manifest import ffmpeg_exe


class FfmpegError(RuntimeError):
    pass


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
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(_bin()),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
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
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if on_proc is not None:
        on_proc(proc)
    try:
        while True:
            if cancel is not None and cancel.is_set():
                _kill(proc)
                raise RuntimeError("cancelled")
            try:
                proc.wait(timeout=0.12)
                break
            except subprocess.TimeoutExpired:
                continue
        stderr = proc.stderr.read() if proc.stderr else ""
        if proc.returncode != 0 or not dest.is_file():
            raise FfmpegError((stderr or "").strip() or "ffmpeg_failed")
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
