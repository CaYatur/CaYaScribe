from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cayascribe.asr.router import resolve_asr_language
from cayascribe.assets.manifest import whisper_dir_for_quality
from cayascribe.perf import configure_threads, cpu_thread_count, decode_params

_MODEL_CACHE: dict[str, tuple[Any, str, str]] = {}
_MODEL_LOCK = threading.Lock()


def clear_model_cache() -> None:
    _MODEL_CACHE.clear()


def _cuda_device_count() -> int:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return 0


def _load_win_dll(name: str) -> bool:
    try:
        import ctypes

        ctypes.WinDLL(name)
        return True
    except OSError:
        return False


def _is_windows() -> bool:
    return os.name == "nt"


def cublas_available() -> bool:
    """CTranslate2 CUDA builds need cuBLAS 12. A GPU driver alone is not enough."""
    if _is_windows():
        return _load_win_dll("cublas64_12.dll")
    try:
        import ctypes

        ctypes.CDLL("libcublas.so.12")
        return True
    except OSError:
        return False


def cuda_usable() -> bool:
    return _cuda_device_count() > 0 and cublas_available()


def device_and_compute() -> tuple[str, str]:
    if cuda_usable():
        return "cuda", "float16"
    return "cpu", "int8"


def open_whisper_model(model_dir: Path | str) -> tuple[Any, str, str]:
    from faster_whisper import WhisperModel

    configure_threads()
    threads = cpu_thread_count()
    device, compute = device_and_compute()
    resolved = str(Path(model_dir))
    key = f"{resolved}|{device}|{compute}|{threads}"
    with _MODEL_LOCK:
        hit = _MODEL_CACHE.get(key)
        if hit is not None:
            return hit
    try:
        model = WhisperModel(
            resolved,
            device=device,
            compute_type=compute,
            cpu_threads=threads if device == "cpu" else 0,
            num_workers=1,
            local_files_only=True,
        )
        loaded = (model, device, compute)
    except Exception:
        if device == "cpu":
            raise
        cpu_key = f"{resolved}|cpu|int8|{threads}"
        with _MODEL_LOCK:
            hit = _MODEL_CACHE.get(cpu_key)
            if hit is not None:
                return hit
        model = WhisperModel(
            resolved,
            device="cpu",
            compute_type="int8",
            cpu_threads=threads,
            num_workers=1,
            local_files_only=True,
        )
        loaded = (model, "cpu", "int8")
        key = cpu_key
    with _MODEL_LOCK:
        _MODEL_CACHE[key] = loaded
    return loaded


def detect_language(
    wav: Path,
    cancel: threading.Event | None = None,
    model_dir: Path | None = None,
) -> str | None:
    """Whisper LID on the first ~30s. Qwen-ONNX auto-LID is unreliable for Turkish."""
    if cancel is not None and cancel.is_set():
        return None
    if model_dir is None:
        for quality in ("fast", "balanced", "max"):
            _name, found = whisper_dir_for_quality(quality)
            if found is not None:
                model_dir = found
                break
    if model_dir is None:
        return None
    import numpy as np
    import soundfile as sf

    samples, sr = sf.read(str(wav), dtype="float32")
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    take = min(samples.shape[0], int(sr * 30))
    if take < sr:
        return None
    clip = np.ascontiguousarray(samples[:take], dtype=np.float32)
    model, _device, _compute = open_whisper_model(model_dir)
    _segments, info = model.transcribe(
        clip,
        language=None,
        vad_filter=True,
        word_timestamps=False,
        without_timestamps=True,
        beam_size=1,
        best_of=1,
        temperature=0.0,
        condition_on_previous_text=False,
        language_detection_segments=1,
    )
    lang = getattr(info, "language", None)
    conf = float(getattr(info, "language_probability", 1.0) or 0.0)
    if not lang:
        return None
    if conf < 0.4:
        return None
    return str(lang)


def transcribe(
    wav: Path,
    quality: str,
    language: str,
    model_dir: Path | None = None,
    cancel: threading.Event | None = None,
) -> Iterator[dict[str, Any]]:
    if cancel is not None and cancel.is_set():
        return
    if model_dir is None:
        _name, model_dir = whisper_dir_for_quality(quality)
    if model_dir is None:
        raise RuntimeError("asr_model_missing")
    model, device, compute = open_whisper_model(model_dir)
    lang = resolve_asr_language(language)
    duration = 0.0
    try:
        import soundfile as sf

        duration = float(sf.info(str(wav)).duration or 0.0)
    except Exception:
        duration = 0.0
    params = decode_params(quality)
    segments, info = model.transcribe(
        str(wav),
        language=lang,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400, "speech_pad_ms": 200},
        word_timestamps=False,
        condition_on_previous_text=False,
        beam_size=int(params["beam_size"]),
        best_of=int(params["best_of"]),
        temperature=float(params["temperature"]),
    )
    detected = getattr(info, "language", language or "auto")
    if duration <= 0:
        duration = float(getattr(info, "duration", 0.0) or 0.0)
    yield {
        "type": "meta",
        "language": detected,
        "engine": f"faster-whisper:{model_dir.name}",
        "device": device,
        "compute": compute,
    }
    yield {
        "type": "progress",
        "stage": "asr",
        "stagePct": 0,
        "stageDone": 0,
        "stageTotal": int(duration) if duration > 0 else 0,
    }
    for i, seg in enumerate(segments):
        if cancel is not None and cancel.is_set():
            return
        end_s = float(getattr(seg, "end", 0.0) or 0.0)
        if duration > 0:
            stage_pct = min(100, int(100 * end_s / duration))
            yield {
                "type": "progress",
                "stage": "asr",
                "stagePct": stage_pct,
                "stageDone": int(end_s),
                "stageTotal": int(duration),
            }
        text = (seg.text or "").strip()
        if not text:
            continue
        yield {
            "type": "segment",
            "id": f"s{i:04d}",
            "startMs": int(seg.start * 1000),
            "endMs": int(seg.end * 1000),
            "text": text,
            "words": [],
        }
