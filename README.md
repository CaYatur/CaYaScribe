# CaYaScribe

Local, offline speaker-aware transcription for Windows. Audio and video **never leave your machine**.

**Languages:** [English](README.md) (default) · [Türkçe](README.tr.md)

The **app UI** is English or Turkish. The OS/browser language is used on first launch; anything other than Turkish falls back to **English**. You can switch in the title bar. Transcription itself covers 99+ languages (Whisper); an unknown language code is treated as English.

## What it does

- Extracts audio from MP3, MP4 and other media (LGPL FFmpeg)
- Transcribes in 99+ languages (Whisper; Turkish and English are first-class)
- Optional speaker diarization: empty count = auto-detect, `1` = single speaker
- Speakers labeled A, B, C… — rename globally in one action
- Export TXT / SRT / VTT / JSON; timestamps are optional
- On first launch, **asks** before downloading missing models; you can also download later from Models

## Releases

Windows installers are published on [GitHub Releases](https://github.com/CaYatur/CaYaScribe/releases).

- Push a tag `vX.Y.Z` to build NSIS (`.exe`) and attach it to the release
- Models are **not** inside the installer; the app downloads them after you consent
- v0.1 still expects the Python sidecar for transcription (see development setup)

See [docs/releasing.md](docs/releasing.md).

## Development setup

Requires: Windows 10+, Python 3.12+, Node 20+, Rust (Tauri).

```powershell
# 1) Sidecar venv
cd sidecar/python
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\pip install -e ".[dev]"

# 2) Desktop
cd ..\..\apps\desktop
npm install
npm run tauri dev
```

On first run the app offers FFmpeg, Qwen3-ASR 0.6B/1.7B (Turkish and noisy audio), pyannote segmentation, and WeSpeaker ResNet293-LM (speaker ID). Uncheck what you do not need.

## Quality profiles

| Profile | Engine (v0.1) |
| --- | --- |
| Fast | Whisper `small` |
| Balanced (default) | Whisper `large-v3-turbo` |
| High | Qwen3-ASR 0.6B (CPU ONNX) when downloaded; else turbo |
| Maximum | Qwen3-ASR 1.7B when downloaded; else 0.6B or Whisper `large-v3` |

Speaker diarization is language-independent (sherpa-onnx + TitaNet). No Hugging Face token is required for the default path.

## Privacy

- Speech-to-text never goes to the cloud
- Downloads happen only after you confirm, from Hugging Face / GitHub
- No telemetry

Architecture: [`docs/design.md`](docs/design.md)

## License

App code: [MIT](LICENSE). Third-party: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
