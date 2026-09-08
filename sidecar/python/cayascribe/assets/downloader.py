from __future__ import annotations

import hashlib
import os
import shutil
import tarfile
import tempfile
import threading
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from cayascribe.assets.manifest import AssetRecord
from cayascribe.paths import assets_dir as assets_root


class DownloadManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._busy = False
        self._progress: dict = {
            "active": False,
            "assetId": None,
            "bytes": 0,
            "total": 0,
            "error": None,
        }

    @property
    def progress(self) -> dict:
        with self._lock:
            return dict(self._progress)

    def cancel(self) -> None:
        self._cancel.set()

    def start(self, record: AssetRecord, on_event=None) -> None:
        self.start_many([record], on_event)

    def start_many(self, records: list[AssetRecord], on_event=None) -> None:
        with self._lock:
            if self._busy:
                raise RuntimeError("download_busy")
            self._busy = True
            self._cancel.clear()
            first = records[0]
            self._progress = {
                "active": True,
                "assetId": first.id,
                "bytes": 0,
                "total": first.sizeBytes or 0,
                "error": None,
            }

        def _all() -> None:
            try:
                for rec in records:
                    if self._cancel.is_set():
                        raise RuntimeError("cancelled")
                    with self._lock:
                        self._progress = {
                            "active": True,
                            "assetId": rec.id,
                            "bytes": 0,
                            "total": rec.sizeBytes or 0,
                            "error": None,
                        }
                    self._run_one(rec, on_event)
                    if on_event:
                        on_event("asset_done", {"id": rec.id})
            except Exception as exc:
                with self._lock:
                    self._progress["error"] = str(exc)
                if on_event:
                    on_event("asset_error", {"id": None, "error": str(exc)})
            finally:
                with self._lock:
                    self._busy = False
                    self._progress["active"] = False

        threading.Thread(target=_all, daemon=True).start()

    def _run_one(self, record: AssetRecord, on_event) -> None:
        dest_parent = (assets_root() / record.relativePath).parent
        dest_parent.mkdir(parents=True, exist_ok=True)
        if record.hfRepo:
            self._hf(record, on_event)
        elif record.urls:
            url = record.urls[0]
            if url.endswith((".zip", ".tar.bz2", ".tbz2")):
                self._archive(record, url, on_event)
            else:
                self._file(record, url, on_event)
        else:
            raise RuntimeError("no_url")

    def _set_bytes(self, n: int, total: int | None = None) -> None:
        with self._lock:
            self._progress["bytes"] = n
            if total:
                self._progress["total"] = total

    def _hf(self, record: AssetRecord, on_event) -> None:
        # Downloader child: Hub is allowed here only.
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        from huggingface_hub import snapshot_download

        target = assets_root() / record.relativePath
        snapshot_download(
            repo_id=record.hfRepo,
            local_dir=str(target),
        )
        os.environ["HF_HUB_OFFLINE"] = "1"
        if on_event:
            on_event("asset_progress", {"id": record.id, "bytes": record.sizeBytes, "total": record.sizeBytes})

    def _file(self, record: AssetRecord, url: str, on_event) -> None:
        dest = assets_root() / record.relativePath
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        self._http_to(url, tmp, record, on_event)
        tmp.replace(dest)

    def _archive(self, record: AssetRecord, url: str, on_event) -> None:
        suffix = ".zip" if url.endswith(".zip") else ".tar.bz2"
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / f"dl{suffix}"
            self._http_to(url, archive, record, on_event)
            extract_dir = Path(td) / "out"
            extract_dir.mkdir()
            if suffix == ".zip":
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(extract_dir)
            else:
                with tarfile.open(archive, "r:bz2") as tf:
                    tf.extractall(extract_dir)
            if record.extract == "ffmpeg":
                ffmpeg = next(extract_dir.rglob("ffmpeg.exe"), None)
                ffprobe = next(extract_dir.rglob("ffprobe.exe"), None)
                if not ffmpeg:
                    raise RuntimeError("ffmpeg_missing_in_zip")
                dest = assets_root() / record.relativePath
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ffmpeg, dest)
                if ffprobe:
                    shutil.copy2(ffprobe, dest.parent / "ffprobe.exe")
                # license smoke: must not be GPL
                # checked later via `ffmpeg -version`
            elif record.archiveRoot:
                dest = assets_root() / record.archiveRoot
                if dest.exists():
                    shutil.rmtree(dest)
                inner = extract_dir
                kids = list(extract_dir.iterdir())
                if len(kids) == 1 and kids[0].is_dir():
                    inner = kids[0]
                shutil.copytree(inner, dest)
            else:
                raise RuntimeError("unknown_archive_layout")

    def _http_to(self, url: str, dest: Path, record: AssetRecord, on_event) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        existing = dest.stat().st_size if dest.exists() else 0
        headers = {"User-Agent": "CaYaScribe/0.1"}
        if existing:
            headers["Range"] = f"bytes={existing}-"
        req = Request(url, headers=headers)
        with urlopen(req, timeout=60) as resp:
            total = existing + int(resp.headers.get("Content-Length") or 0)
            mode = "ab" if existing and resp.status == 206 else "wb"
            if mode == "wb":
                existing = 0
            written = existing
            hasher = hashlib.sha256()
            if existing and dest.exists():
                with dest.open("rb") as prev:
                    for chunk in iter(lambda: prev.read(1024 * 1024), b""):
                        hasher.update(chunk)
            with dest.open(mode) as f:
                while True:
                    if self._cancel.is_set():
                        raise RuntimeError("cancelled")
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    hasher.update(chunk)
                    written += len(chunk)
                    self._set_bytes(written, total or record.sizeBytes)
                    if on_event:
                        on_event(
                            "asset_progress",
                            {"id": record.id, "bytes": written, "total": total or record.sizeBytes},
                        )
        if record.sha256:
            digest = hasher.hexdigest()
            if digest.lower() != record.sha256.lower():
                dest.unlink(missing_ok=True)
                raise RuntimeError("sha256_mismatch")
