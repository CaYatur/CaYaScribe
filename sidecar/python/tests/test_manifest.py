from pathlib import Path

from cayascribe.assets.manifest import AssetRecord, ct2_model_dir


def _asr() -> AssetRecord:
    return AssetRecord(
        id="whisper-turbo-ct2",
        kind="asr",
        displayName="turbo",
        qualityTiers=["balanced"],
        required=False,
        recommended=True,
        license="MIT",
        gated=False,
        sizeBytes=1,
        sha256=None,
        relativePath="asr/whisper-turbo-ct2",
        urls=[],
        hfRepo="deepdml/faster-whisper-large-v3-turbo-ct2",
    )


def test_ct2_dir_ignores_metadata_only(tmp_path: Path):
    d = tmp_path / "asr"
    d.mkdir()
    (d / "config.json").write_text("{}", encoding="utf-8")
    (d / "README.md").write_text("x", encoding="utf-8")
    (d / ".cache").mkdir()
    (d / ".cache" / "x").write_bytes(b"123")
    assert ct2_model_dir(d, min_bytes=8) is None


def test_ct2_dir_rejects_tiny_weight(tmp_path: Path):
    d = tmp_path / "asr"
    d.mkdir()
    (d / "model.bin").write_bytes(b"ptr")
    assert ct2_model_dir(d, min_bytes=8) is None


def test_ct2_dir_finds_model_bin(tmp_path: Path):
    d = tmp_path / "asr"
    d.mkdir()
    (d / "model.bin").write_bytes(b"0123456789")
    assert ct2_model_dir(d, min_bytes=8) == d


def test_ct2_dir_nested(tmp_path: Path):
    d = tmp_path / "asr"
    inner = d / "repo"
    inner.mkdir(parents=True)
    (inner / "model.safetensors").write_bytes(b"0123456789")
    assert ct2_model_dir(d, min_bytes=8) == inner


def test_asr_present_false_without_weights(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("cayascribe.assets.manifest.MIN_CT2_BYTES", 8)
    d = tmp_path / "asr" / "whisper-turbo-ct2"
    d.mkdir(parents=True)
    (d / "config.json").write_text("{}", encoding="utf-8")
    rec = _asr()
    monkeypatch.setattr(rec, "local_path", lambda: d)
    assert rec.present() is False


def test_asr_present_true_with_model_bin(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("cayascribe.assets.manifest.MIN_CT2_BYTES", 8)
    d = tmp_path / "asr" / "whisper-turbo-ct2"
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"0123456789")
    rec = _asr()
    monkeypatch.setattr(rec, "local_path", lambda: d)
    assert rec.present() is True


def test_disk_bytes_counts_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("cayascribe.assets.manifest.assets_dir", lambda: tmp_path)
    rec = _asr()
    d = tmp_path / "asr" / "whisper-turbo-ct2"
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"0123456789")
    (d / ".cache").mkdir()
    (d / ".cache" / "part").write_bytes(b"abcd")
    assert rec.disk_bytes() == 14


def test_remove_asr_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("cayascribe.assets.manifest.assets_dir", lambda: tmp_path)
    rec = _asr()
    d = tmp_path / "asr" / "whisper-turbo-ct2"
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"0123456789")
    rec.remove()
    assert not d.exists()
    assert rec.disk_bytes() == 0


def test_remove_ffmpeg_folder(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("cayascribe.assets.manifest.assets_dir", lambda: tmp_path)
    rec = AssetRecord(
        id="ffmpeg-btbn-lgpl-8.1",
        kind="ffmpeg",
        displayName="ffmpeg",
        qualityTiers=[],
        required=True,
        recommended=True,
        license="LGPL-2.1+",
        gated=False,
        sizeBytes=1,
        sha256=None,
        relativePath="ffmpeg/ffmpeg.exe",
        urls=[],
        extract="ffmpeg",
    )
    folder = tmp_path / "ffmpeg"
    folder.mkdir()
    (folder / "ffmpeg.exe").write_bytes(b"ff")
    (folder / "ffprobe.exe").write_bytes(b"pr")
    assert rec.disk_bytes() == 4
    rec.remove()
    assert not folder.exists()


def test_remove_refuses_assets_root(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("cayascribe.assets.manifest.assets_dir", lambda: tmp_path)
    rec = AssetRecord(
        id="bad",
        kind="asr",
        displayName="bad",
        qualityTiers=[],
        required=False,
        recommended=False,
        license="MIT",
        gated=False,
        sizeBytes=0,
        sha256=None,
        relativePath=".",
        urls=[],
    )
    keep = tmp_path / "keep.txt"
    keep.write_text("x", encoding="utf-8")
    try:
        rec.remove()
        assert False, "expected refuse_delete_assets_root"
    except RuntimeError as exc:
        assert "refuse_delete_assets_root" in str(exc)
    assert keep.exists()
