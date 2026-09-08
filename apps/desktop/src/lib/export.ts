import { formatClock } from "./format";

export type Segment = {
  id: string;
  speakerId: string;
  startMs: number;
  endMs: number;
  text: string;
};

export type Speaker = { id: string; name: string };

export type ExportOptions = {
  timestamps: boolean;
  speakers: boolean;
};

function nameOf(speakers: Speaker[], id: string): string {
  return speakers.find((s) => s.id === id)?.name ?? id;
}

export function exportTxt(
  segments: Segment[],
  speakers: Speaker[],
  opts: ExportOptions,
): string {
  return segments
    .map((s) => {
      const who = opts.speakers ? `${nameOf(speakers, s.speakerId)}: ` : "";
      const ts = opts.timestamps
        ? `[${formatClock(s.startMs, "txt")} – ${formatClock(s.endMs, "txt")}] `
        : "";
      return `${ts}${who}${s.text}`.trim();
    })
    .join("\n");
}

export function exportSrt(
  segments: Segment[],
  speakers: Speaker[],
  opts: ExportOptions,
): string {
  return segments
    .map((s, i) => {
      const who = opts.speakers ? `${nameOf(speakers, s.speakerId)}: ` : "";
      const head = `${i + 1}\n${formatClock(s.startMs, "srt")} --> ${formatClock(s.endMs, "srt")}`;
      return `${head}\n${who}${s.text}`;
    })
    .join("\n\n");
}

export function exportVtt(
  segments: Segment[],
  speakers: Speaker[],
  opts: ExportOptions,
): string {
  const body = segments
    .map((s) => {
      const who = opts.speakers ? `<v ${nameOf(speakers, s.speakerId)}>` : "";
      return `${formatClock(s.startMs, "vtt")} --> ${formatClock(s.endMs, "vtt")}\n${who}${s.text}`;
    })
    .join("\n\n");
  return `WEBVTT\n\n${body}\n`;
}

export function exportJson(
  segments: Segment[],
  speakers: Speaker[],
  extra: Record<string, unknown> = {},
): string {
  return JSON.stringify({ version: 1, speakers, segments, ...extra }, null, 2);
}
