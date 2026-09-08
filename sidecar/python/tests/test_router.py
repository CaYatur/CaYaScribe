from cayascribe.asr.router import parakeet_allowed, resolve_asr_language, select_engine


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


def test_qwen_needs_cu12x():
    assert (
        select_engine(
            language="tr",
            quality="max",
            qwen_06=True,
            cu12x=True,
            vram_mb=8000,
        )
        == "qwen-0.6b"
    )
    assert (
        select_engine(
            language="tr",
            quality="max",
            qwen_06=True,
            cu12x=False,
            vram_mb=8000,
        )
        == "whisper-large-v3"
    )


def test_forced_qwen_without_cuda_errors():
    try:
        select_engine(language="tr", quality="high", forced="qwen", cu12x=False)
        assert False, "expected error"
    except ValueError as exc:
        assert "engine_runtime_missing" in str(exc)
