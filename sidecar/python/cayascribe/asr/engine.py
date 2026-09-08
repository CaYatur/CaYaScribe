from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cayascribe.asr.qwen_onnx import transcribe_qwen
from cayascribe.asr.router import select_engine
from cayascribe.asr.whisper_fw import transcribe as transcribe_whisper
from cayascribe.assets.manifest import by_id, qwen_model_dir


def _present(asset_id: str) -> bool:
    try:
        return by_id(asset_id).present()
    except KeyError:
        return False


def transcribe(
    wav: Path,
    quality: str,
    language: str,
    turns: list[dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    engine = select_engine(
        language=language,
        quality=quality,
        qwen_06=_present("qwen3-asr-0.6b"),
        qwen_17=_present("qwen3-asr-1.7b"),
    )
    if engine.startswith("qwen"):
        asset_id = "qwen3-asr-1.7b" if engine == "qwen-1.7b" else "qwen3-asr-0.6b"
        model_dir = qwen_model_dir(by_id(asset_id).local_path())
        if model_dir is not None:
            yield from transcribe_qwen(wav, model_dir, language, engine, turns)
            return
    yield from transcribe_whisper(wav, quality, language)
