from __future__ import annotations

import subprocess
from pathlib import Path

from cayascribe.assets.manifest import ffmpeg_exe


class FfmpegError(RuntimeError):
    pass


def _bin() -> Path:
    exe = ffmpeg_exe()
    if not exe:
        raise FfmpegError("ffmpeg_missing")
    return exe


def extract_wav(media: Path, dest: Path, sample_rate: int = 16000) -> Path:
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
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not dest.is_file():
        raise FfmpegError(proc.stderr.strip() or "ffmpeg_failed")
    return dest


def license_ok() -> bool:
    exe = ffmpeg_exe()
    if not exe:
        return False
    proc = subprocess.run([str(exe), "-version"], capture_output=True, text=True, check=False)
    text = (proc.stdout or "") + (proc.stderr or "")
    if "--enable-gpl" in text or "libx264" in text:
        return False
    return proc.returncode == 0
