from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cayascribe.asr.router import resolve_asr_language
from cayascribe.assets.manifest import whisper_dir_for_quality


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

    device, compute = device_and_compute()
    try:
        model = WhisperModel(
            str(model_dir),
            device=device,
            compute_type=compute,
            local_files_only=True,
        )
        return model, device, compute
    except Exception:
        if device == "cpu":
            raise
        model = WhisperModel(
            str(model_dir),
            device="cpu",
            compute_type="int8",
            local_files_only=True,
        )
        return model, "cpu", "int8"


def detect_language(wav: Path, cancel: threading.Event | None = None) -> str | None:
    """Whisper LID on the first ~30s. Qwen-ONNX auto-LID is unreliable for Turkish."""
    if cancel is not None and cancel.is_set():
        return None
    model_dir = None
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
        beam_size=1,
        condition_on_previous_text=False,
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
    segments, info = model.transcribe(
        str(wav),
        language=lang,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=False,
        beam_size=5 if quality in ("high", "max") else 1,
    )
    detected = getattr(info, "language", language or "auto")
    yield {
        "type": "meta",
        "language": detected,
        "engine": f"faster-whisper:{model_dir.name}",
        "device": device,
        "compute": compute,
    }
    for i, seg in enumerate(segments):
        if cancel is not None and cancel.is_set():
            return
        text = (seg.text or "").strip()
        if not text:
            continue
        yield {
            "type": "segment",
            "id": f"s{i:04d}",
            "startMs": int(seg.start * 1000),
            "endMs": int(seg.end * 1000),
            "text": text,
            "words": [
                {
                    "startMs": int(w.start * 1000),
                    "endMs": int(w.end * 1000),
                    "word": w.word,
                }
                for w in (seg.words or [])
            ],
        }
