# Third-party notices

CaYaScribe itself is MIT. Downloaded models and native binaries keep their own licenses. Audio never leaves the machine; these notices apply to local copies.

## Application dependencies

See `apps/desktop/package.json`, `apps/desktop/src-tauri/Cargo.toml`, and `sidecar/python/pyproject.toml`.

## Native binaries (downloaded on consent)

| Asset | License | Source |
| --- | --- | --- |
| FFmpeg BtbN `win64-lgpl` static | LGPL 2.1+ (decode-only; no libx264/libx265) | https://github.com/BtbN/FFmpeg-Builds |
| sherpa-onnx | Apache-2.0 | https://github.com/k2-fsa/sherpa-onnx |

Gyan “essentials” GPLv3 builds are **not** used.

## Models (downloaded on consent, not in git)

| Asset | License | Source |
| --- | --- | --- |
| OpenAI Whisper weights (via faster-whisper CT2) | MIT | https://github.com/openai/whisper |
| Systran faster-whisper conversions | MIT | https://huggingface.co/Systran |
| large-v3-turbo CT2 (`deepdml/faster-whisper-large-v3-turbo-ct2`) | MIT | Hugging Face community conversion |
| Silero VAD (bundled with faster-whisper) | MIT | https://github.com/snakers4/silero-vad |
| sherpa-onnx pyannote segmentation 3.0 | MIT (pyannote.audio model card) | k2-fsa GitHub releases |
| NeMo TitaNet-small speaker embedding ONNX | CC-BY-4.0 | k2-fsa GitHub releases |
| Qwen3-ASR 0.6B INT8 (sherpa-onnx) | Apache-2.0 | k2-fsa GitHub releases / QwenLM |
| Qwen3-ASR 1.7B INT8 (sherpa-onnx) | Apache-2.0 | Hugging Face `thieunv/sherpa-onnx-qwen3-asr-1.7B-int8` / QwenLM |

Parakeet TDT v3 (CC-BY-4.0) is EU-only and is not used for Turkish. CUDA extras remain optional.
