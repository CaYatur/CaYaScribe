"""Bounded reads and silence-aware splits for long media.

faster-whisper VAD/FFT and sherpa-onnx diarization OOM on hour-scale files when
the whole waveform is loaded as float32. We never need more than one chunk in RAM.
"""

from __future__ import annotations

from pathlib import Path


def wav_duration(path: Path) -> float:
    import soundfile as sf

    return float(sf.info(str(path)).duration or 0.0)


def wav_sample_rate(path: Path) -> int:
    import soundfile as sf

    return int(sf.info(str(path)).samplerate or 16000)


def read_slice(path: Path, start_s: float, end_s: float):
    """Return (float32 mono samples, sample_rate) for [start_s, end_s)."""
    import numpy as np
    import soundfile as sf

    info = sf.info(str(path))
    sr = int(info.samplerate or 16000)
    n = int(info.frames or 0)
    start = max(0, min(n, int(start_s * sr)))
    stop = max(start, min(n, int(end_s * sr)))
    frames = stop - start
    if frames <= 0:
        return np.zeros(0, dtype=np.float32), sr
    samples, _sr = sf.read(str(path), dtype="float32", start=start, frames=frames)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    return np.ascontiguousarray(samples, dtype=np.float32), sr


def _quietest_time(path: Path, center_s: float, search_s: float = 6.0) -> float:
    """Snap a split to the quietest short hop near center_s."""
    import numpy as np

    lo = max(0.0, center_s - search_s)
    hi = center_s + search_s
    audio, sr = read_slice(path, lo, hi)
    if audio.size < sr * 0.4:
        return center_s
    hop = max(1, int(sr * 0.05))
    win = max(hop, int(sr * 0.25))
    best_i = 0
    best_e = float("inf")
    i = 0
    while i + win <= audio.size:
        e = float(np.mean(audio[i : i + win] ** 2))
        if e < best_e:
            best_e = e
            best_i = i
        i += hop
    return lo + best_i / float(sr)


def plan_chunks(
    duration: float,
    max_sec: float,
    *,
    path: Path | None = None,
) -> list[tuple[float, float]]:
    """Split [0, duration] into pieces of about max_sec.

    Interior edges snap to nearby silence when `path` is a wav we can read.
    A leftover shorter than 25% of max_sec is absorbed into the previous piece.
    """
    if duration <= 0:
        return [(0.0, 0.0)]
    if duration <= max_sec * 1.25:
        return [(0.0, duration)]
    bounds = [0.0]
    t = max_sec
    while t < duration - max_sec * 0.25:
        edge = t
        if path is not None:
            try:
                edge = _quietest_time(path, t)
            except Exception:
                edge = t
        if edge <= bounds[-1] + 30:
            edge = min(duration, bounds[-1] + max_sec)
        bounds.append(min(duration, max(bounds[-1] + 30, edge)))
        t = bounds[-1] + max_sec
    if bounds[-1] < duration:
        bounds.append(duration)
    out: list[tuple[float, float]] = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        if b > a + 0.2:
            out.append((a, b))
    return out or [(0.0, duration)]
