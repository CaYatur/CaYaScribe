from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cayascribe.paths import assets_dir, bundled_manifest

QUALITY_ASR = {
    "fast": ("whisper-small-ct2", "small"),
    "balanced": ("whisper-turbo-ct2", "large-v3-turbo"),
    "high": ("whisper-turbo-ct2", "large-v3-turbo"),
    "max": ("whisper-large-v3-ct2", "large-v3"),
}

# CTranslate2 weights; git-LFS pointers are ~130 bytes. 50 MiB is below Whisper-small.
MIN_CT2_BYTES = 50 * 1024 * 1024
_CT2_NAMES = ("model.bin", "model.safetensors")
_SKIP_DIRS = {".cache", ".git", "__pycache__"}


def _is_ct2_weight(path: Path, min_bytes: int) -> bool:
    return path.is_file() and path.stat().st_size >= min_bytes


def ct2_model_dir(path: Path, *, min_bytes: int | None = None) -> Path | None:
    """Directory that actually contains CTranslate2 weights, or None if incomplete."""
    if min_bytes is None:
        min_bytes = MIN_CT2_BYTES
    if not path.exists():
        return None
    if path.is_file():
        return path.parent if path.name in _CT2_NAMES and _is_ct2_weight(path, min_bytes) else None
    if not path.is_dir():
        return None
    if any(_is_ct2_weight(path / name, min_bytes) for name in _CT2_NAMES):
        return path
    for child in path.iterdir():
        if not child.is_dir() or child.name in _SKIP_DIRS or child.name.startswith("."):
            continue
        if any(_is_ct2_weight(child / name, min_bytes) for name in _CT2_NAMES):
            return child
    return None


@dataclass
class AssetRecord:
    id: str
    kind: str
    displayName: str
    qualityTiers: list[str]
    required: bool
    recommended: bool
    license: str
    gated: bool
    sizeBytes: int
    sha256: str | None
    relativePath: str
    urls: list[str]
    hfRepo: str | None = None
    extract: str | None = None
    archiveRoot: str | None = None

    def local_path(self) -> Path:
        return assets_dir() / self.relativePath

    def present(self) -> bool:
        p = self.local_path()
        if self.kind == "asr":
            return ct2_model_dir(p) is not None
        if p.is_file():
            return p.stat().st_size > 0
        if p.is_dir():
            return any(f.is_file() and f.stat().st_size > 0 for f in p.rglob("*") if ".cache" not in f.parts)
        return False

    def source_label(self) -> str:
        if self.hfRepo:
            return f"Hugging Face · {self.hfRepo}"
        if self.urls:
            u = self.urls[0]
            if "github.com" in u:
                return "GitHub Releases"
            return u
        return ""


def load_manifest() -> list[AssetRecord]:
    path = bundled_manifest()
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[AssetRecord] = []
    for raw in data["assets"]:
        out.append(
            AssetRecord(
                id=raw["id"],
                kind=raw["kind"],
                displayName=raw["displayName"],
                qualityTiers=list(raw.get("qualityTiers") or []),
                required=bool(raw.get("required")),
                recommended=bool(raw.get("recommended")),
                license=raw["license"],
                gated=bool(raw.get("gated")),
                sizeBytes=int(raw.get("sizeBytes") or 0),
                sha256=raw.get("sha256"),
                relativePath=raw["relativePath"],
                urls=list(raw.get("urls") or []),
                hfRepo=raw.get("hfRepo"),
                extract=raw.get("extract"),
                archiveRoot=raw.get("archiveRoot"),
            )
        )
    return out


def asset_status(records: list[AssetRecord] | None = None) -> list[dict[str, Any]]:
    records = records or load_manifest()
    rows = []
    for a in records:
        present = a.present()
        rows.append(
            {
                "id": a.id,
                "kind": a.kind,
                "displayName": a.displayName,
                "qualityTiers": a.qualityTiers,
                "required": a.required,
                "recommended": a.recommended,
                "license": a.license,
                "gated": a.gated,
                "sizeBytes": a.sizeBytes,
                "present": present,
                "path": str(a.local_path()),
                "source": a.source_label(),
                "hfRepo": a.hfRepo,
            }
        )
    return rows


def by_id(asset_id: str) -> AssetRecord:
    for a in load_manifest():
        if a.id == asset_id:
            return a
    raise KeyError(asset_id)


def ffmpeg_exe() -> Path | None:
    try:
        rec = by_id("ffmpeg-btbn-lgpl-8.1")
    except KeyError:
        return None
    p = rec.local_path()
    return p if p.is_file() else None


def quality_ready(quality: str) -> bool:
    if ffmpeg_exe() is None:
        return False
    asset_id, _ = QUALITY_ASR.get(quality, QUALITY_ASR["balanced"])
    return by_id(asset_id).present()


def whisper_dir_for_quality(quality: str) -> tuple[str, Path | None]:
    asset_id, name = QUALITY_ASR.get(quality, QUALITY_ASR["balanced"])
    rec = by_id(asset_id)
    return name, ct2_model_dir(rec.local_path())
