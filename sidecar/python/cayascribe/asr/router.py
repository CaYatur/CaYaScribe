from __future__ import annotations

# Whisper large-v3 language codes. Anything else falls back to English.
WHISPER_LANGS = {
    "af", "am", "ar", "as", "az", "ba", "be", "bg", "bn", "bo", "br", "bs", "ca",
    "cs", "cy", "da", "de", "el", "en", "es", "et", "eu", "fa", "fi", "fo", "fr",
    "gl", "gu", "ha", "haw", "he", "hi", "hr", "ht", "hu", "hy", "id", "is", "it",
    "ja", "jw", "ka", "kk", "km", "kn", "ko", "la", "lb", "ln", "lo", "lt", "lv",
    "mg", "mi", "mk", "ml", "mn", "mr", "ms", "mt", "my", "ne", "nl", "nn", "no",
    "oc", "pa", "pl", "ps", "pt", "ro", "ru", "sa", "sd", "si", "sk", "sl", "sn",
    "so", "sq", "sr", "su", "sv", "sw", "ta", "te", "tg", "th", "tk", "tl", "tr",
    "tt", "uk", "ur", "uz", "vi", "yi", "yo", "yue", "zh",
}


def resolve_asr_language(language: str) -> str | None:
    """None = auto-detect. Unsupported codes become English."""
    lang = (language or "auto").strip().lower()
    if lang in ("auto", "", "detect"):
        return None
    if lang not in WHISPER_LANGS:
        return "en"
    return lang


PARAKEET_25 = {
    "bg", "hr", "cs", "da", "nl", "en", "et", "fi", "fr", "de", "el", "hu",
    "it", "lv", "lt", "mt", "pl", "pt", "ro", "sk", "sl", "es", "sv", "ru", "uk",
}

QWEN_LANGS = {
    "zh", "en", "yue", "ar", "de", "fr", "es", "pt", "id", "it", "ko", "ru",
    "th", "vi", "ja", "tr", "hi", "ms", "nl", "sv", "da", "fi", "pl", "cs",
    "fil", "fa", "el", "hu", "mk", "ro",
}

QWEN_LANG_NAMES = {
    "zh": "Chinese",
    "en": "English",
    "yue": "Cantonese",
    "ar": "Arabic",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "pt": "Portuguese",
    "id": "Indonesian",
    "it": "Italian",
    "ko": "Korean",
    "ru": "Russian",
    "th": "Thai",
    "vi": "Vietnamese",
    "ja": "Japanese",
    "tr": "Turkish",
    "hi": "Hindi",
    "ms": "Malay",
    "nl": "Dutch",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "pl": "Polish",
    "cs": "Czech",
    "fil": "Filipino",
    "fa": "Persian",
    "el": "Greek",
    "hu": "Hungarian",
    "mk": "Macedonian",
    "ro": "Romanian",
}


def qwen_language_ok(language: str) -> bool:
    lang = (language or "auto").strip().lower()
    if lang in ("auto", "", "detect"):
        return True
    if lang == "tl":
        lang = "fil"
    return lang in QWEN_LANGS


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
    whisper_tr: bool = False,
    cu12x: bool = False,
    vram_mb: int = 0,
    parakeet: bool = False,
    forced: str | None = None,
) -> str:
    lang = (language or "auto").lower()
    if lang == "tl":
        lang = "fil"
    if forced == "parakeet" and lang == "tr":
        raise ValueError("parakeet_forbidden_for_tr")
    if forced == "qwen":
        if qwen_17:
            return "qwen-1.7b"
        if qwen_06:
            return "qwen-0.6b"
        raise ValueError("asr_model_missing")
    if forced:
        return forced

    lang_auto = (language or "auto").strip().lower() in ("auto", "", "detect")
    # Independent FLEURS-TR: Whisper turbo ~6% WER, Qwen3-ASR 1.7B ~9%.
    # Do not send Turkish to Qwen. Prefer the TR Whisper large-v3 fine-tune.
    if lang == "tr" and quality in ("high", "max"):
        if whisper_tr:
            return "whisper-large-v3-tr"
        if quality == "max":
            return "whisper-large-v3"
        return "whisper-turbo"
    # Qwen-ONNX wins on some languages (zh/yue/th/vi/hi), not Turkish.
    if (not lang_auto) and lang != "tr" and quality in ("high", "max") and qwen_language_ok(lang):
        if qwen_06:
            return "qwen-0.6b"
        if qwen_17:
            return "qwen-1.7b"

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
