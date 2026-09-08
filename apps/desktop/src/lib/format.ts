export function formatClock(ms: number, style: "txt" | "srt" | "vtt"): string {
  const clamped = Math.max(0, ms);
  const h = Math.floor(clamped / 3_600_000);
  const m = Math.floor((clamped % 3_600_000) / 60_000);
  const s = Math.floor((clamped % 60_000) / 1000);
  const frac = clamped % 1000;
  const pad = (n: number, w = 2) => String(n).padStart(w, "0");
  if (style === "txt") {
    const mm = h * 60 + m;
    return `${pad(mm)}:${pad(s)}.${String(frac).padStart(3, "0").slice(0, 1)}`;
  }
  if (style === "srt") {
    return `${pad(h)}:${pad(m)}:${pad(s)},${pad(frac, 3)}`;
  }
  return `${pad(h)}:${pad(m)}:${pad(s)}.${pad(frac, 3)}`;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
