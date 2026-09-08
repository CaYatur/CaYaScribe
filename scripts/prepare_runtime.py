"""Build sidecar/runtime: Windows embeddable CPython + wheels + cayascribe."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_VER = "3.12.10"
EMBED_URL = f"https://www.python.org/ftp/python/{PY_VER}/python-{PY_VER}-embed-amd64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"download {url}")
    urllib.request.urlretrieve(url, dest)


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print("run", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def _write_pth(runtime: Path) -> None:
    matches = list(runtime.glob("python*._pth"))
    if not matches:
        raise SystemExit("python._pth missing in embeddable zip")
    matches[0].write_text(
        "python312.zip\n.\nLib\\site-packages\nimport site\n",
        encoding="utf-8",
    )


def prepare(dest: Path, *, force: bool) -> None:
    if dest.exists() and force:
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    py = dest / "python.exe"
    if not py.is_file():
        zpath = dest / "_python-embed.zip"
        _download(EMBED_URL, zpath)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(dest)
        zpath.unlink(missing_ok=True)
        _write_pth(dest)
    else:
        _write_pth(dest)

    get_pip = dest / "get-pip.py"
    if not get_pip.is_file():
        _download(GET_PIP_URL, get_pip)
    _run([str(py), str(get_pip), "--no-warn-script-location"], cwd=dest)
    sidecar = ROOT / "sidecar" / "python"
    _run(
        [
            str(py),
            "-m",
            "pip",
            "install",
            "--no-warn-script-location",
            "--upgrade",
            "pip",
            "setuptools",
            "wheel",
        ],
        cwd=dest,
    )
    _run(
        [str(py), "-m", "pip", "install", "--no-warn-script-location", str(sidecar)],
        cwd=dest,
    )
    assets_src = ROOT / "assets" / "manifest.json"
    assets_dest = dest / "assets"
    assets_dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(assets_src, assets_dest / "manifest.json")
    _run(
        [
            str(py),
            "-c",
            "import cayascribe.server, faster_whisper, sherpa_onnx, onnxruntime, ctranslate2, soundfile; print('runtime-ok')",
        ],
        cwd=dest,
    )
    print(f"runtime ready: {dest}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", type=Path, default=ROOT / "sidecar" / "runtime")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        prepare(args.dest, force=args.force)
    except subprocess.CalledProcessError as exc:
        print(exc, file=sys.stderr)
        return exc.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
