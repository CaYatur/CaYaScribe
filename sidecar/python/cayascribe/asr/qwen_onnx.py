from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cayascribe.asr.router import QWEN_LANG_NAMES, resolve_asr_language

CHUNK_MS = 20_000


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
    return QWEN_LANG_NAMES.get(code, "")


def _chunks(
    n: int,
    sr: int,
    turns: list[dict[str, Any]] | None,
) -> list[tuple[int, int]]:
    if turns:
        out: list[tuple[int, int]] = []
        win = int(CHUNK_MS * sr / 1000)
        for t in turns:
            a = max(0, int(int(t["startMs"]) * sr / 1000))
            b = min(n, int(int(t["endMs"]) * sr / 1000))
            i = a
            while i < b:
                j = min(b, i + win)
                if j - i >= int(0.25 * sr):
                    out.append((i, j))
                i = j
        if out:
            return out
    win = int(CHUNK_MS * sr / 1000)
    out = []
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
    import numpy as np
    import sherpa_onnx
    import soundfile as sf

    conv, enc, dec, tok = _files(model_dir)
    threads = max(1, min(4, os.cpu_count() or 2))
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
        "language": lang_opt or language or "auto",
        "engine": f"{engine_name}:{model_dir.name}",
        "device": "cpu",
        "compute": "int8",
    }
    idx = 0
    for start, end in _chunks(audio.shape[0], sr, turns):
        piece = audio[start:end]
        if piece.size < sr * 0.25:
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
        text = (getattr(stream.result, "text", "") or "").strip()
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
