from __future__ import annotations

import os


def total_ram_bytes() -> int | None:
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return int(stat.ullTotalPhys)
        except Exception:
            return None
        return None
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except Exception:
        return None


def ram_gb() -> float | None:
    raw = total_ram_bytes()
    if raw is None:
        return None
    return raw / (1024**3)


def cpu_thread_count() -> int:
    n = os.cpu_count() or 4
    gb = ram_gb()
    if gb is not None:
        if gb < 8:
            n = min(n, 2)
        elif gb < 12:
            n = min(n, 4)
        else:
            n = min(n, 8)
    else:
        n = min(n, 8)
    return max(2, int(n))


def asr_chunk_seconds() -> int:
    gb = ram_gb()
    if gb is not None and gb < 8:
        return 5 * 60
    if gb is not None and gb < 12:
        return 8 * 60
    return 10 * 60


def diar_chunk_seconds() -> int:
    gb = ram_gb()
    if gb is not None and gb < 8:
        return 6 * 60
    if gb is not None and gb < 12:
        return 8 * 60
    return 10 * 60


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
