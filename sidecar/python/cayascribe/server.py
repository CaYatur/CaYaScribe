from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from cayascribe.assets.downloader import DownloadManager
from cayascribe.assets.manifest import asset_status, by_id
from cayascribe.auth import require_bearer
from cayascribe.models import JobCreate
from cayascribe.offline import apply_inference_offline
from cayascribe.pipeline.ffmpeg import license_ok
from cayascribe.pipeline.jobs import RUNNER

apply_inference_offline()

app = FastAPI(title="CaYaScribe sidecar", version="0.1.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOADS = DownloadManager()
_asset_events: list[tuple[str, dict[str, Any]]] = []


def _on_asset(event: str, data: dict[str, Any]) -> None:
    _asset_events.append((event, data))


@app.get("/v1/health")
def health() -> dict[str, Any]:
    return {"ok": True, "name": "cayascribe", "version": "0.1.1"}


@app.get("/v1/devices", dependencies=[Depends(require_bearer)])
def devices() -> dict[str, Any]:
    from cayascribe.asr.whisper_fw import cuda_usable

    return {"cuda": cuda_usable(), "vramMb": 0, "ffmpegLgpl": license_ok()}


@app.get("/v1/assets", dependencies=[Depends(require_bearer)])
def assets() -> dict[str, Any]:
    rows = asset_status()
    missing = [r for r in rows if not r["present"]]
    return {
        "assets": rows,
        "missingRequired": [r for r in missing if r["required"]],
        "diskTotal": sum(int(r.get("diskBytes") or 0) for r in rows),
    }


@app.post("/v1/assets/download", dependencies=[Depends(require_bearer)])
def download(body: dict[str, Any]) -> dict[str, Any]:
    ids = body.get("ids") or []
    if not ids:
        raise HTTPException(400, "no_ids")
    recs = [by_id(i) for i in ids]
    try:
        DOWNLOADS.start_many(recs, on_event=_on_asset)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"started": recs[0].id, "queued": ids[1:], "progress": DOWNLOADS.progress}


@app.post("/v1/assets/cancel", dependencies=[Depends(require_bearer)])
def cancel_download() -> dict[str, str]:
    DOWNLOADS.cancel()
    return {"ok": "cancelled"}


@app.post("/v1/assets/remove", dependencies=[Depends(require_bearer)])
def remove_assets(body: dict[str, Any]) -> dict[str, Any]:
    if RUNNER.busy():
        raise HTTPException(409, "job_running")
    if DOWNLOADS.progress.get("active"):
        raise HTTPException(409, "download_busy")
    ids = body.get("ids") or []
    if not ids:
        raise HTTPException(400, "no_ids")
    removed: list[str] = []
    for asset_id in ids:
        try:
            rec = by_id(asset_id)
        except KeyError as exc:
            raise HTTPException(404, f"unknown_asset:{asset_id}") from exc
        try:
            rec.remove()
        except OSError as exc:
            raise HTTPException(409, f"remove_failed:{asset_id}:{exc}") from exc
        removed.append(asset_id)
    rows = asset_status()
    return {
        "removed": removed,
        "assets": rows,
        "diskTotal": sum(int(r.get("diskBytes") or 0) for r in rows),
    }


@app.get("/v1/assets/progress", dependencies=[Depends(require_bearer)])
def asset_progress() -> dict[str, Any]:
    return DOWNLOADS.progress


@app.get("/v1/assets/events", dependencies=[Depends(require_bearer)])
async def asset_events():
    async def gen():
        idx = 0
        while True:
            while idx < len(_asset_events):
                ev, data = _asset_events[idx]
                idx += 1
                yield f"event: {ev}\ndata: {json.dumps(data)}\n\n"
            p = DOWNLOADS.progress
            yield f"event: progress\ndata: {json.dumps(p)}\n\n"
            if not p.get("active"):
                await asyncio.sleep(0.4)
            else:
                await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/v1/jobs", dependencies=[Depends(require_bearer)])
def create_job(req: JobCreate) -> dict[str, str]:
    if RUNNER.busy():
        raise HTTPException(409, "job_running")
    try:
        job_id = RUNNER.start(req)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"jobId": job_id}


@app.post("/v1/jobs/{job_id}/cancel", dependencies=[Depends(require_bearer)])
def cancel_job(job_id: str) -> dict[str, str]:
    RUNNER.cancel(job_id)
    return {"ok": "cancelled"}


@app.get("/v1/jobs/{job_id}", dependencies=[Depends(require_bearer)])
def get_job(job_id: str) -> dict[str, Any]:
    result = RUNNER.result(job_id)
    if result:
        return result
    return {"jobId": job_id, "events": len(RUNNER.events(job_id))}


@app.get("/v1/jobs/{job_id}/events", dependencies=[Depends(require_bearer)])
async def job_events(job_id: str):
    async def gen():
        idx = 0
        while True:
            events = RUNNER.events(job_id)
            while idx < len(events):
                ev, data = events[idx]
                idx += 1
                yield f"event: {ev}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if ev in ("done", "error", "cancelled"):
                    return
            await asyncio.sleep(0.2)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/v1/shutdown", dependencies=[Depends(require_bearer)])
def shutdown() -> dict[str, str]:
    return {"ok": "bye"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("CAYA_PORT", "8765")))
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost"):
        print("refusing non-loopback bind", file=sys.stderr)
        sys.exit(2)
    if not os.environ.get("CAYA_TOKEN"):
        os.environ["CAYA_TOKEN"] = "dev-token"
        print("CAYA_TOKEN defaulted to dev-token (development only)", file=sys.stderr)
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
