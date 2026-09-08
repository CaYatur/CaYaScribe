from pathlib import Path

import pytest

from cayascribe.offline import assert_local_media
from cayascribe.paths import bundled_manifest


def test_rejects_http():
    with pytest.raises(ValueError):
        assert_local_media("https://example.com/a.mp3")


def test_rejects_unc():
    with pytest.raises(ValueError):
        assert_local_media(r"\\server\share\a.mp3")


def test_bundled_manifest_env(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CAYA_MANIFEST", str(manifest))
    assert bundled_manifest() == manifest
