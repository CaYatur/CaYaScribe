from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cayascribe.asr.router import QWEN_LANG_NAMES, resolve_asr_language

CHUNK_MS = 30_000


def _files(model_dir: Path) -> tuple[str, str, str, str]:
    conv = model_dir / "conv_frontend.onnx"
    tok = model_dir / "tokenizer"
    enc = next(iter(model_dir.glob("encoder*.onnx")), None)
    dec = next(iter(model_dir.glob("decoder*.onnx")), None)
    if not conv.is_file() or not tok.is_dir() or enc is None or dec is None:
        raise RuntimeError("qwen_model_incomplete")
    return str(conv), str(enc), str(dec), str(tok)


def _language_option(language: str) -> str:
    code = resolve_asr_language(language)
    if not code:
        return ""
    if code == "tl":
        code = "fil"
    return QWEN_LANG_NAMES.get(code, "")


def cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    n = 0
    for ch in text:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF or 0x3040 <= o <= 0x30FF or 0xAC00 <= o <= 0xD7AF:
            n += 1
    return n / max(len(text), 1)


def _clean_text(raw: str) -> str:
    t = (raw or "").strip()
    if "<asr_text>" in t:
        t = t.split("<asr_text>", 1)[-1]
    if t.lower().startswith("language "):
        t = t.split("\n", 1)[-1]
        if "<asr_text>" in t:
            t = t.split("<asr_text>", 1)[-1]
    return t.strip()


def _chunks(n: int, sr: int) -> list[tuple[int, int]]:
    # Do not slice by diarization turns — that re-runs Qwen dozens of times.
    win = int(CHUNK_MS * sr / 1000)
    out: list[tuple[int, int]] = []
    i = 0
    while i < n:
        out.append((i, min(n, i + win)))
        i += win
    return out or [(0, n)]


def transcribe_qwen(
    wav: Path,
    model_dir: Path,
    language: str,
    engine_name: str,
    turns: list[dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    _ = turns
    import numpy as np
    import sherpa_onnx
    import soundfile as sf

    conv, enc, dec, tok = _files(model_dir)
    threads = max(2, min(8, os.cpu_count() or 2))
    rec = sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
        conv_frontend=conv,
        encoder=enc,
        decoder=dec,
        tokenizer=tok,
        num_threads=threads,
        sample_rate=16000,
        feature_dim=128,
        provider="cpu",
        max_total_len=1024,
        max_new_tokens=256,
    )
    samples, sr = sf.read(str(wav), dtype="float32")
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    audio = np.ascontiguousarray(samples, dtype=np.float32)
    lang_opt = _language_option(language)
    yield {
        "type": "meta",
        "language": resolve_asr_language(language) or language or "auto",
        "engine": f"{engine_name}:{model_dir.name}",
        "device": "cpu",
        "compute": "int8",
    }
    windows = _chunks(audio.shape[0], int(sr))
    idx = 0
    for wi, (start, end) in enumerate(windows):
        yield {
            "type": "progress",
            "stage": "asr",
            "pct": 35 + int(50 * wi / max(len(windows), 1)),
        }
        piece = audio[start:end]
        if piece.size < sr * 0.35:
            continue
        if float(np.max(np.abs(piece))) < 0.008:
            continue
        stream = rec.create_stream()
        if lang_opt:
            try:
                stream.set_option("language", lang_opt)
            except Exception:
                pass
        stream.accept_waveform(int(sr), piece)
        rec.decode_stream(stream)
        text = _clean_text(getattr(stream.result, "text", "") or "")
        if not text:
            continue
        yield {
            "type": "segment",
            "id": f"s{idx:04d}",
            "startMs": int(start * 1000 / sr),
            "endMs": int(end * 1000 / sr),
            "text": text,
            "words": [],
        }
        idx += 1
