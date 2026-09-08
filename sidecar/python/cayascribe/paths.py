from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("CAYA_DATA_DIR")
    if override:
        p = Path(override)
    else:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        p = Path(local) / "CaYaScribe"
    p.mkdir(parents=True, exist_ok=True)
    return p


def assets_dir() -> Path:
    p = data_dir() / "assets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def jobs_dir() -> Path:
    p = data_dir() / "jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return data_dir() / "config.json"


def bundled_manifest() -> Path:
    env = os.environ.get("CAYA_MANIFEST")
    if env:
        p = Path(env)
        if p.is_file():
            return p
    here = Path(__file__).resolve()
    exe_dir = Path(sys.executable).resolve().parent
    candidates: list[Path] = [exe_dir / "assets" / "manifest.json"]
    for idx in (3, 1):
        if len(here.parents) > idx:
            candidates.append(here.parents[idx] / "assets" / "manifest.json")
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]
