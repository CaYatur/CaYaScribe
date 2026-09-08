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
        if p.is_file():
            return p.stat().st_size > 0
        if p.is_dir():
            return any(p.rglob("*"))
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
    if rec.present():
        return name, rec.local_path()
    return name, None
