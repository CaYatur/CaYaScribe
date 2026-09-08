from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cayascribe.assets.manifest import whisper_dir_for_quality


def device_and_compute() -> tuple[str, str]:
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def transcribe(
    wav: Path,
    quality: str,
    language: str,
) -> Iterator[dict[str, Any]]:
    from faster_whisper import WhisperModel

    _name, model_dir = whisper_dir_for_quality(quality)
    if model_dir is None:
        raise RuntimeError("asr_model_missing")
    device, compute = device_and_compute()
    model = WhisperModel(
        str(model_dir),
        device=device,
        compute_type=compute,
        local_files_only=True,
    )
    lang = None if language in ("auto", "", "detect") else language
    segments, info = model.transcribe(
        str(wav),
        language=lang,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=False,
        beam_size=5 if quality in ("high", "max") else 1,
    )
    detected = getattr(info, "language", language or "auto")
    yield {"type": "meta", "language": detected, "engine": f"faster-whisper:{model_dir.name}", "device": device}
    for i, seg in enumerate(segments):
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
