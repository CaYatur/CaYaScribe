from __future__ import annotations

import os


def cpu_thread_count() -> int:
    n = os.cpu_count() or 4
    return max(4, min(16, int(n)))


def configure_threads() -> int:
    n = cpu_thread_count()
    os.environ.setdefault("OMP_NUM_THREADS", str(n))
    os.environ.setdefault("MKL_NUM_THREADS", str(n))
    os.environ.setdefault("OPENBLAS_NUM_THREADS", str(n))
    os.environ.setdefault("NUMEXPR_NUM_THREADS", str(n))
    os.environ.setdefault("CT2_INTER_THREADS", "1")
    os.environ.setdefault("CT2_INTRA_THREADS", str(n))
    return n


def decode_params(quality: str) -> dict[str, int | float]:
    """Greedy/low-beam decode. Default faster-whisper best_of=5 is very slow."""
    if quality == "max":
        return {"beam_size": 5, "best_of": 1, "temperature": 0.0}
    if quality == "high":
        return {"beam_size": 2, "best_of": 1, "temperature": 0.0}
    return {"beam_size": 1, "best_of": 1, "temperature": 0.0}
