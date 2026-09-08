from __future__ import annotations

import os
from pathlib import Path

INFERENCE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "PYANNOTE_METRICS_ENABLED": "0",
}


def apply_inference_offline() -> None:
    for key, value in INFERENCE_ENV.items():
        os.environ[key] = value
    try:
        from huggingface_hub import constants

        constants.HF_HUB_OFFLINE = True
    except Exception:
        pass


def allow_hub_download() -> None:
    """Downloads must hit Hugging Face / GitHub. Inference stays offline otherwise."""
    os.environ["HF_HUB_OFFLINE"] = "0"
    os.environ["TRANSFORMERS_OFFLINE"] = "0"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    try:
        from huggingface_hub import constants

        constants.HF_HUB_OFFLINE = False
    except Exception:
        pass


def assert_local_media(path: str) -> Path:
    raw = path.strip()
    lowered = raw.lower()
    if lowered.startswith(("http://", "https://", "file:", "ftp://", "rtsp://", "hls:")):
        raise ValueError("remote_media_rejected")
    if raw.startswith(("\\\\", "//")):
        raise ValueError("unc_rejected")
    p = Path(raw)
    if not p.exists() or not p.is_file():
        raise ValueError("not_a_file")
    return p.resolve()
