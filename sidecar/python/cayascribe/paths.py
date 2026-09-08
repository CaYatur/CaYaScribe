from __future__ import annotations

import os
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
    here = Path(__file__).resolve()
    # sidecar/python/cayascribe/paths.py → repo assets/manifest.json
    return here.parents[3] / "assets" / "manifest.json"
