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


def test_high_tr_prefers_whisper_tr_finetune():
    assert (
        select_engine(
            language="tr",
            quality="high",
            qwen_06=True,
            whisper_tr=True,
        )
        == "whisper-large-v3-tr"
    )


def test_tr_never_selects_qwen():
    assert (
        select_engine(
            language="tr",
            quality="max",
            qwen_06=True,
            qwen_17=True,
            whisper_tr=False,
        )
        == "whisper-large-v3"
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


def test_high_quality_ids_prefer_whisper_tr():
    assert QUALITY_ASR_IDS["high"][0] == "whisper-large-v3-tr"
    assert QUALITY_ASR_IDS["max"][0] == "whisper-large-v3-tr"


def test_manifest_quality_tiers_per_model():
    from cayascribe.assets.manifest import by_id

    assert by_id("whisper-small-ct2").qualityTiers == ["fast"]
    assert by_id("whisper-turbo-ct2").qualityTiers == ["balanced", "high"]
    assert by_id("whisper-large-v3-ct2").qualityTiers == ["max"]
    assert by_id("whisper-large-v3-tr").qualityTiers == ["high", "max"]


def test_engine_asset_covers_forced_ids():
    from cayascribe.asr.engine import ENGINE_ASSET

    assert ENGINE_ASSET["whisper-turbo"] == "whisper-turbo-ct2"
    assert ENGINE_ASSET["whisper-large-v3-tr"] == "whisper-large-v3-tr"
    assert ENGINE_ASSET["qwen-0.6b"] == "qwen3-asr-0.6b"


def test_jobcreate_blank_model_ids_are_none():
    from cayascribe.models import JobCreate

    job = JobCreate(mediaPath=r"C:\a.wav", asrId="", embedId="auto")
    assert job.asrId is None
    assert job.embedId is None
    job2 = JobCreate(mediaPath=r"C:\a.wav", asrId="whisper-turbo-ct2", embedId="titanet-small")
    assert job2.asrId == "whisper-turbo-ct2"
    assert job2.embedId == "titanet-small"
