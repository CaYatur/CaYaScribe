import { en, type Messages } from "./en";
import { tr } from "./tr";

export type Locale = "en" | "tr";

const KEY = "cayascribe.locale";

/** Only `tr` and `en` are UI locales. Any other language (de, fr, ja, …) → English. */
export function localeFromNavigator(lang: string): Locale {
  const nav = lang.toLowerCase();
  if (nav === "tr" || nav.startsWith("tr-")) return "tr";
  return "en";
}

export function detectLocale(): Locale {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored === "en" || stored === "tr") return stored;
  } catch {
    /* ignore */
  }
  const nav = typeof navigator !== "undefined" ? navigator.language : "en";
  return localeFromNavigator(nav);
}

export function persistLocale(locale: Locale): void {
  try {
    localStorage.setItem(KEY, locale);
  } catch {
    /* ignore */
  }
}

export function messages(locale: Locale): Messages {
  return locale === "tr" ? tr : en;
}

export function assetLabel(locale: Locale, id: string, fallback: string): string {
  return messages(locale).assets[id] ?? fallback;
}

export function stageLabel(locale: Locale, stage: string): string {
  const t = messages(locale);
  switch (stage) {
    case "starting":
      return t.stageStarting;
    case "extract":
      return t.stageExtract;
    case "diarize":
      return t.stageDiarize;
    case "asr":
      return t.stageAsr;
    case "done":
      return t.stageDone;
    case "error":
      return t.stageError;
    default:
      return stage;
  }
}
