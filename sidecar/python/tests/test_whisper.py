from cayascribe.asr.whisper_fw import (
    cublas_available,
    cuda_usable,
    device_and_compute,
    open_whisper_model,
)


def test_device_cpu_when_cuda_unusable(monkeypatch):
    monkeypatch.setattr("cayascribe.asr.whisper_fw.cuda_usable", lambda: False)
    assert device_and_compute() == ("cpu", "int8")


def test_device_cuda_when_usable(monkeypatch):
    monkeypatch.setattr("cayascribe.asr.whisper_fw.cuda_usable", lambda: True)
    assert device_and_compute() == ("cuda", "float16")


def test_cuda_usable_needs_cublas(monkeypatch):
    monkeypatch.setattr("cayascribe.asr.whisper_fw._cuda_device_count", lambda: 1)
    monkeypatch.setattr("cayascribe.asr.whisper_fw.cublas_available", lambda: False)
    assert cuda_usable() is False
    monkeypatch.setattr("cayascribe.asr.whisper_fw.cublas_available", lambda: True)
    assert cuda_usable() is True


def test_cublas_false_when_dll_missing(monkeypatch):
    monkeypatch.setattr("cayascribe.asr.whisper_fw._is_windows", lambda: True)
    monkeypatch.setattr("cayascribe.asr.whisper_fw._load_win_dll", lambda _name: False)
    assert cublas_available() is False


def test_open_whisper_falls_back_to_cpu(monkeypatch):
    class Boom:
        def __init__(self, _path, *, device, compute_type, local_files_only):
            if device == "cuda":
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
            self.device = device
            self.compute_type = compute_type
            assert local_files_only is True

    monkeypatch.setattr("cayascribe.asr.whisper_fw.device_and_compute", lambda: ("cuda", "float16"))
    monkeypatch.setattr("faster_whisper.WhisperModel", Boom)
    model, device, compute = open_whisper_model("unused")
    assert device == "cpu"
    assert compute == "int8"
    assert model.device == "cpu"
