from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cayascribe.asr.qwen_onnx import cjk_ratio, transcribe_qwen
from cayascribe.asr.router import resolve_asr_language, select_engine
from cayascribe.asr.whisper_fw import detect_language
from cayascribe.asr.whisper_fw import transcribe as transcribe_whisper
from cayascribe.assets.manifest import by_id, ct2_model_dir, qwen_model_dir


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
    lang = language
    if resolve_asr_language(language) is None:
        detected = detect_language(wav)
        if detected:
            lang = detected
    engine = select_engine(
        language=lang,
        quality=quality,
        qwen_06=_present("qwen3-asr-0.6b"),
        qwen_17=_present("qwen3-asr-1.7b"),
        whisper_tr=_present("whisper-large-v3-tr"),
    )
    if engine == "whisper-large-v3-tr":
        model_dir = ct2_model_dir(by_id("whisper-large-v3-tr").local_path())
        if model_dir is not None:
            yield from transcribe_whisper(wav, quality, lang or "tr", model_dir=model_dir)
            return
    if engine.startswith("qwen"):
        asset_id = "qwen3-asr-1.7b" if engine == "qwen-1.7b" else "qwen3-asr-0.6b"
        model_dir = qwen_model_dir(by_id(asset_id).local_path())
        if model_dir is not None:
            gen = transcribe_qwen(wav, model_dir, lang, engine, turns)
            prelude: list[dict[str, Any]] = []
            first_seg: dict[str, Any] | None = None
            for item in gen:
                if item.get("type") == "segment":
                    first_seg = item
                    break
                prelude.append(item)
            code = resolve_asr_language(lang) or ""
            if first_seg and code == "tr" and cjk_ratio(str(first_seg.get("text") or "")) > 0.12:
                yield from transcribe_whisper(wav, quality, lang)
                return
            for item in prelude:
                if item.get("type") == "meta" and lang and lang not in ("auto", ""):
                    item = {**item, "language": lang}
                yield item
            if first_seg:
                yield first_seg
            yield from gen
            return
    yield from transcribe_whisper(wav, quality, lang)
