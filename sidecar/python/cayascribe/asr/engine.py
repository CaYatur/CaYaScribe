from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cayascribe.asr.qwen_onnx import cjk_ratio, transcribe_qwen
from cayascribe.asr.router import resolve_asr_language, select_engine
from cayascribe.asr.whisper_fw import detect_language
from cayascribe.asr.whisper_fw import transcribe as transcribe_whisper
from cayascribe.assets.manifest import by_id, ct2_model_dir, qwen_model_dir

ENGINE_ASSET = {
    "whisper-small": "whisper-small-ct2",
    "whisper-medium": "whisper-medium-ct2",
    "whisper-turbo": "whisper-turbo-ct2",
    "whisper-large-v3": "whisper-large-v3-ct2",
    "whisper-large-v3-tr": "whisper-large-v3-tr",
    "qwen-0.6b": "qwen3-asr-0.6b",
    "qwen-1.7b": "qwen3-asr-1.7b",
}


def _present(asset_id: str) -> bool:
    try:
        return by_id(asset_id).present()
    except KeyError:
        return False


def _transcribe_asset(
    asset_id: str,
    wav: Path,
    quality: str,
    lang: str,
    turns: list[dict[str, Any]] | None,
    cancel: threading.Event | None,
    *,
    forced: bool,
) -> Iterator[dict[str, Any]]:
    rec = by_id(asset_id)
    if rec.kind != "asr" or not rec.present():
        raise RuntimeError("asr_model_missing")
    if asset_id.startswith("qwen3-asr"):
        engine_name = "qwen-1.7b" if asset_id.endswith("1.7b") else "qwen-0.6b"
        model_dir = qwen_model_dir(rec.local_path())
        if model_dir is None:
            raise RuntimeError("asr_model_missing")
        gen = transcribe_qwen(wav, model_dir, lang, engine_name, turns, cancel=cancel)
        if forced:
            yield from gen
            return
        prelude: list[dict[str, Any]] = []
        first_seg: dict[str, Any] | None = None
        for item in gen:
            if cancel is not None and cancel.is_set():
                return
            if item.get("type") == "segment":
                first_seg = item
                break
            prelude.append(item)
        code = resolve_asr_language(lang) or ""
        if first_seg and code == "tr" and cjk_ratio(str(first_seg.get("text") or "")) > 0.12:
            yield from transcribe_whisper(wav, quality, lang, cancel=cancel)
            return
        for item in prelude:
            if item.get("type") == "meta" and lang and lang not in ("auto", ""):
                item = {**item, "language": lang}
            yield item
        if first_seg:
            yield first_seg
        for item in gen:
            if cancel is not None and cancel.is_set():
                return
            yield item
        return
    model_dir = ct2_model_dir(rec.local_path())
    if model_dir is None:
        raise RuntimeError("asr_model_missing")
    yield from transcribe_whisper(wav, quality, lang, model_dir=model_dir, cancel=cancel)


def transcribe(
    wav: Path,
    quality: str,
    language: str,
    turns: list[dict[str, Any]] | None = None,
    cancel: threading.Event | None = None,
    asr_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    if cancel is not None and cancel.is_set():
        return
    lang = language
    lid_dir = None
    if asr_id and not asr_id.startswith("qwen"):
        try:
            lid_dir = ct2_model_dir(by_id(asr_id).local_path())
        except KeyError:
            lid_dir = None
    if resolve_asr_language(language) is None:
        detected = detect_language(wav, cancel=cancel, model_dir=lid_dir)
        if cancel is not None and cancel.is_set():
            return
        if detected:
            lang = detected
    if asr_id:
        yield from _transcribe_asset(
            asr_id, wav, quality, lang or language, turns, cancel, forced=True
        )
        return
    engine = select_engine(
        language=lang,
        quality=quality,
        qwen_06=_present("qwen3-asr-0.6b"),
        qwen_17=_present("qwen3-asr-1.7b"),
        whisper_tr=_present("whisper-large-v3-tr"),
    )
    asset_id = ENGINE_ASSET.get(engine)
    if asset_id and _present(asset_id):
        yield from _transcribe_asset(
            asset_id, wav, quality, lang or language, turns, cancel, forced=False
        )
        return
    yield from transcribe_whisper(wav, quality, lang, cancel=cancel)
