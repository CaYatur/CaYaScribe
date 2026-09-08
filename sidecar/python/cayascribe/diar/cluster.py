from __future__ import annotations

from pathlib import Path
from typing import Any

from cayascribe.assets.manifest import by_id
from cayascribe.paths import assets_dir


def speaker_letter(i: int) -> str:
    if i < 26:
        return chr(ord("A") + i)
    return f"S{i + 1}"


def diarize(wav: Path, speaker_count: int | None) -> list[dict[str, Any]]:
    """Return turns [{startMs,endMs,speakerId}] or empty if models missing."""
    try:
        seg = by_id("pyannote-seg-3").local_path()
        emb = by_id("titanet-small").local_path()
    except KeyError:
        return []
    if not seg.is_file() or not emb.is_file():
        # segmentation may live as model.onnx inside extracted dir
        seg_dir = assets_dir() / "diar" / "segmentation"
        cand = seg_dir / "model.onnx"
        if cand.is_file():
            seg = cand
        else:
            found = list(seg_dir.rglob("*.onnx")) if seg_dir.exists() else []
            if found:
                seg = found[0]
            else:
                return []
        if not emb.is_file():
            return []

    import numpy as np
    import sherpa_onnx
    import soundfile as sf

    samples, sr = sf.read(str(wav), dtype="float32")
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    if sr != 16000:
        raise RuntimeError("diar_expects_16k")

    num_clusters = int(speaker_count) if speaker_count and speaker_count >= 2 else -1
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(seg)),
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(emb)),
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
    result = sd.process(np.ascontiguousarray(samples, dtype=np.float32))
    turns = []
    # first-appearance labeling A, B, C
    order: dict[int, str] = {}
    for item in result:
        sid = int(item.speaker)
        if sid not in order:
            order[sid] = speaker_letter(len(order))
        turns.append(
            {
                "startMs": int(item.start * 1000),
                "endMs": int(item.end * 1000),
                "speakerId": order[sid],
            }
        )
    return turns


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
