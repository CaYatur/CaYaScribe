from cayascribe.asr.router import parakeet_allowed, resolve_asr_language, select_engine
from cayascribe.assets.manifest import QUALITY_ASR, QUALITY_ASR_IDS


def test_quality_maps_to_exact_whisper_repo():
    assert QUALITY_ASR["fast"][0] == "whisper-small-ct2"
    assert QUALITY_ASR["balanced"][0] == "whisper-turbo-ct2"
    assert QUALITY_ASR["max"][0] == "whisper-large-v3-ct2"


def test_unsupported_language_falls_back_to_english():
    assert resolve_asr_language("auto") is None
    assert resolve_asr_language("tr") == "tr"
    assert resolve_asr_language("en") == "en"
    assert resolve_asr_language("xx") == "en"
    assert resolve_asr_language("klingon") == "en"


def test_parakeet_never_for_turkish():
    assert parakeet_allowed("tr", "tr") is False
    assert parakeet_allowed("tr", "en") is False
    assert parakeet_allowed("en", "tr") is False
    assert parakeet_allowed("auto", "tr") is False


def test_parakeet_ok_for_eu_when_locale_en():
    assert parakeet_allowed("de", "en") is True
    assert parakeet_allowed("en", "en") is True


def test_max_tr_without_qwen_is_whisper():
    assert select_engine(language="tr", quality="max", ui_locale="tr") == "whisper-large-v3"


def test_high_tr_prefers_qwen_onnx_without_cuda():
    assert (
        select_engine(
            language="tr",
            quality="high",
            qwen_06=True,
            cu12x=False,
        )
        == "qwen-0.6b"
    )


def test_max_tr_uses_qwen_06_on_cpu():
    assert (
        select_engine(
            language="tr",
            quality="max",
            qwen_06=True,
            qwen_17=True,
            cu12x=False,
        )
        == "qwen-0.6b"
    )


def test_auto_does_not_select_qwen():
    assert (
        select_engine(
            language="auto",
            quality="high",
            qwen_06=True,
            qwen_17=True,
        )
        == "whisper-turbo"
    )


def test_forced_qwen_uses_onnx_without_cuda():
    assert select_engine(language="tr", quality="high", forced="qwen", qwen_06=True, cu12x=False) == "qwen-0.6b"


def test_cjk_ratio_detects_chinese():
    from cayascribe.asr.qwen_onnx import cjk_ratio

    assert cjk_ratio("merhaba nasılsın") < 0.05
    assert cjk_ratio("你好世界 hello") > 0.3


def test_high_quality_ids_prefer_qwen():
    assert QUALITY_ASR_IDS["high"][0] == "qwen3-asr-0.6b"
    assert QUALITY_ASR_IDS["max"][0] == "qwen3-asr-1.7b"
