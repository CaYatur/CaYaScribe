from __future__ import annotations

PARAKEET_25 = {
    "bg", "hr", "cs", "da", "nl", "en", "et", "fi", "fr", "de", "el", "hu",
    "it", "lv", "lt", "mt", "pl", "pt", "ro", "sk", "sl", "es", "sv", "ru", "uk",
}

QWEN_LANGS = {
    "zh", "en", "yue", "ar", "de", "fr", "es", "pt", "id", "it", "ko", "ru",
    "th", "vi", "ja", "tr", "hi", "ms", "nl", "sv", "da", "fi", "pl", "cs",
    "fil", "fa", "el", "hu", "mk", "ro",
}


def parakeet_allowed(language: str, ui_locale: str, lid_confidence: float = 1.0) -> bool:
    lang = (language or "auto").lower()
    if lang == "tr":
        return False
    if ui_locale.lower().startswith("tr") and lang in ("auto", "en"):
        return False
    if lang == "auto":
        return False
    if lid_confidence < 0.65:
        return False
    return lang in PARAKEET_25


def select_engine(
    *,
    language: str,
    quality: str,
    ui_locale: str = "tr",
    qwen_06: bool = False,
    qwen_17: bool = False,
    cu12x: bool = False,
    vram_mb: int = 0,
    parakeet: bool = False,
    forced: str | None = None,
) -> str:
    lang = (language or "auto").lower()
    if forced == "parakeet" and lang == "tr":
        raise ValueError("parakeet_forbidden_for_tr")
    if forced == "qwen" and not cu12x:
        raise ValueError("engine_runtime_missing")
    if forced:
        return forced

    if lang in QWEN_LANGS and quality in ("high", "max") and cu12x:
        if qwen_17 and vram_mb >= 12288:
            return "qwen-1.7b"
        if qwen_06 and vram_mb >= 6144:
            return "qwen-0.6b"

    if (
        parakeet
        and quality in ("fast", "balanced")
        and parakeet_allowed(lang, ui_locale)
    ):
        return "parakeet"

    if quality == "fast":
        return "whisper-small"
    if quality == "max":
        return "whisper-large-v3"
    return "whisper-turbo"
