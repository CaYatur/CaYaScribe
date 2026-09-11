from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cayascribe.assets.manifest import by_id
from cayascribe.audio.chunks import plan_chunks, read_slice, wav_duration
from cayascribe.paths import assets_dir
from cayascribe.perf import cpu_thread_count, diar_chunk_seconds, ram_gb

_DIAR_CACHE: dict[tuple[str, str, int, int], Any] = {}

# Best-available embedding first. TitaNet-small is a fallback only.
EMBED_IDS = [
    "wespeaker-resnet293-lm",
    "eres2net-large",
    "titanet-large",
    "titanet-small",
]


def speaker_letter(i: int) -> str:
    if i < 26:
        return chr(ord("A") + i)
    return f"S{i + 1}"


def iter_diar_segments(result: Any) -> list[Any]:
    """sherpa-onnx 1.13 returns OfflineSpeakerDiarizationResult, not a list.

    Official API: `sd.process(audio).sort_by_start_time()` is iterable.
    """
    if result is None:
        return []
    sorted_result = result
    sorter = getattr(result, "sort_by_start_time", None)
    if callable(sorter):
        try:
            sorted_result = sorter()
        except Exception:
            sorted_result = result
    if isinstance(sorted_result, (list, tuple)):
        return list(sorted_result)
    for attr in ("segments",):
        inner = getattr(sorted_result, attr, None)
        if inner is not None and inner is not sorted_result:
            return iter_diar_segments(inner)
    try:
        return list(sorted_result)
    except TypeError:
        return []


def _onnx_file(path: Path) -> Path | None:
    if path.is_file() and path.suffix.lower() == ".onnx" and path.stat().st_size > 0:
        return path
    if path.is_dir():
        preferred = path / "model.onnx"
        if preferred.is_file():
            return preferred
        found = sorted(path.rglob("*.onnx"))
        if found:
            return found[0]
    return None


def segmentation_path() -> Path | None:
    try:
        rec = by_id("pyannote-seg-3")
    except KeyError:
        rec = None
    if rec is not None:
        found = _onnx_file(rec.local_path())
        if found is None:
            found = _onnx_file(rec.install_root())
        if found is not None:
            return found
    seg_dir = assets_dir() / "diar" / "segmentation"
    return _onnx_file(seg_dir)


def embedding_path(embed_id: str | None = None) -> Path | None:
    ids = [embed_id] if embed_id else list(EMBED_IDS)
    for asset_id in ids:
        if not asset_id:
            continue
        try:
            rec = by_id(asset_id)
        except KeyError:
            continue
        found = _onnx_file(rec.local_path())
        if found is None:
            found = _onnx_file(rec.install_root())
        if found is not None:
            return found
    return None


def diarize(
    wav: Path,
    speaker_count: int | None,
    cancel: threading.Event | None = None,
    embed_id: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Return turns [{startMs,endMs,speakerId}] or empty if models missing."""
    if cancel is not None and cancel.is_set():
        raise RuntimeError("cancelled")
    seg = segmentation_path()
    emb = embedding_path(embed_id)
    if seg is None or emb is None:
        return []

    import gc

    import numpy as np
    import sherpa_onnx

    duration = wav_duration(wav)
    num_clusters = int(speaker_count) if speaker_count and speaker_count >= 2 else -1
    threads = cpu_thread_count()
    cache_key = (str(seg), str(emb), num_clusters, threads)
    sd = _DIAR_CACHE.get(cache_key)
    if sd is None:
        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(seg)),
                num_threads=threads,
                provider="cpu",
            ),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=str(emb),
                num_threads=threads,
                provider="cpu",
            ),
            clustering=sherpa_onnx.FastClusteringConfig(
                num_clusters=num_clusters,
                threshold=0.5,
            ),
            min_duration_on=0.3,
            min_duration_off=0.5,
        )
        if not config.validate():
            return []
        sd = sherpa_onnx.OfflineSpeakerDiarization(config)
        _DIAR_CACHE[cache_key] = sd
    expected = int(getattr(sd, "sample_rate", 16000) or 16000)
    pieces = plan_chunks(duration, diar_chunk_seconds(), path=wav)
    overlap_s = 12.0 if len(pieces) > 1 else 0.0

    def _progress(processed: int, total: int) -> int:
        if cancel is not None and cancel.is_set():
            return 1
        if on_progress is not None and total:
            on_progress(int(processed), int(total))
        return 0

    def _turns_from_audio(audio, offset_s: float) -> list[dict[str, Any]]:
        try:
            result = sd.process(audio, callback=_progress)
        except TypeError:
            result = sd.process(audio)
        local: list[dict[str, Any]] = []
        order: dict[int, str] = {}
        for item in iter_diar_segments(result):
            sid = int(getattr(item, "speaker", 0))
            if sid not in order:
                order[sid] = speaker_letter(len(order))
            local.append(
                {
                    "startMs": int((offset_s + float(getattr(item, "start", 0.0))) * 1000),
                    "endMs": int((offset_s + float(getattr(item, "end", 0.0))) * 1000),
                    "speakerId": order[sid],
                }
            )
        return local

    windows: list[list[dict[str, Any]]] = []
    for i, (a, b) in enumerate(pieces):
        if cancel is not None and cancel.is_set():
            raise RuntimeError("cancelled")
        start = max(0.0, a - (overlap_s if i else 0.0))
        audio, sr = read_slice(wav, start, b)
        if audio.size == 0:
            windows.append([])
            continue
        if sr != expected and sr > 0:
            dur = audio.shape[0] / float(sr)
            n = max(1, round(dur * expected))
            t_old = np.linspace(0.0, dur, audio.shape[0], endpoint=False)
            t_new = np.linspace(0.0, dur, n, endpoint=False)
            audio = np.interp(t_new, t_old, audio).astype(np.float32)
        windows.append(_turns_from_audio(audio, start))
        del audio
        gc.collect()
        if on_progress is not None:
            on_progress(i + 1, len(pieces))
    if cancel is not None and cancel.is_set():
        raise RuntimeError("cancelled")
    turns = stitch_window_turns(windows)
    gb = ram_gb()
    if gb is not None and gb < 12:
        clear_diar_cache()
        gc.collect()
    return turns


def clear_diar_cache() -> None:
    _DIAR_CACHE.clear()


def stitch_window_turns(windows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Map per-window speaker letters onto a global A, B, C… timeline."""
    if not windows:
        return []
    out: list[dict[str, Any]] = [dict(t) for t in windows[0]]
    used = {t["speakerId"] for t in out}

    def _fresh() -> str:
        i = 0
        while speaker_letter(i) in used:
            i += 1
        sid = speaker_letter(i)
        used.add(sid)
        return sid

    def _overlap(a: dict[str, Any], b: dict[str, Any]) -> int:
        return max(0, min(a["endMs"], b["endMs"]) - max(a["startMs"], b["startMs"]))

    for window in windows[1:]:
        if not window:
            continue
        win_start = min(t["startMs"] for t in window)
        prev = [t for t in out if t["endMs"] > win_start]
        loc_ids = []
        for t in window:
            if t["speakerId"] not in loc_ids:
                loc_ids.append(t["speakerId"])
        loc_to_glob: dict[str, str] = {}
        for loc in loc_ids:
            loc_turns = [t for t in window if t["speakerId"] == loc]
            best_g = None
            best_o = 0
            for g in {t["speakerId"] for t in prev}:
                g_turns = [t for t in prev if t["speakerId"] == g]
                ov = sum(_overlap(a, b) for a in loc_turns for b in g_turns)
                if ov > best_o:
                    best_o = ov
                    best_g = g
            loc_to_glob[loc] = best_g if best_g is not None and best_o >= 400 else _fresh()
        prev_end = max((t["endMs"] for t in out), default=0)
        for t in window:
            mapped = {**t, "speakerId": loc_to_glob[t["speakerId"]]}
            if mapped["endMs"] <= prev_end:
                continue
            mapped["startMs"] = max(mapped["startMs"], prev_end)
            if mapped["endMs"] > mapped["startMs"]:
                out.append(mapped)
    out.sort(key=lambda t: (t["startMs"], t["endMs"]))
    return out


def assign_speakers(segments: list[dict[str, Any]], turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not turns:
        for s in segments:
            s["speakerId"] = "A"
        return segments
    for s in segments:
        mid = (s["startMs"] + s["endMs"]) // 2
        best = "A"
        overlap = -1
        for t in turns:
            o = min(s["endMs"], t["endMs"]) - max(s["startMs"], t["startMs"])
            if o > overlap:
                overlap = o
                best = t["speakerId"]
            if t["startMs"] <= mid < t["endMs"]:
                best = t["speakerId"]
                break
        s["speakerId"] = best
    return segments
