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

export async function exportDocx(
  segments: Segment[],
  speakers: Speaker[],
  opts: ExportOptions,
  title = "Transcript",
): Promise<Uint8Array> {
  const { Document, HeadingLevel, Packer, Paragraph, TextRun } = await import("docx");
  const children: InstanceType<typeof Paragraph>[] = [
    new Paragraph({
      heading: HeadingLevel.HEADING_1,
      spacing: { after: 280 },
      children: [
        new TextRun({
          text: title,
          bold: true,
          font: "Arial",
          size: 32,
          color: "111826",
        }),
      ],
    }),
  ];
  for (const s of segments) {
    const runs: InstanceType<typeof TextRun>[] = [];
    if (opts.timestamps) {
      runs.push(
        new TextRun({
          text: `${formatClock(s.startMs, "txt")} – ${formatClock(s.endMs, "txt")}  `,
          font: "Arial",
          size: 18,
          color: "64748B",
        }),
      );
    }
    if (opts.speakers) {
      runs.push(
        new TextRun({
          text: `${nameOf(speakers, s.speakerId)}: `,
          bold: true,
          font: "Arial",
          size: 22,
          color: "DC2626",
        }),
      );
    }
    runs.push(
      new TextRun({
        text: s.text,
        font: "Arial",
        size: 22,
        color: "111826",
      }),
    );
    children.push(
      new Paragraph({
        spacing: { after: 200, line: 276 },
        children: runs,
      }),
    );
  }
  if (segments.length === 0) {
    children.push(
      new Paragraph({
        children: [new TextRun({ text: " ", font: "Arial", size: 22 })],
      }),
    );
  }
  const doc = new Document({
    styles: {
      default: { document: { run: { font: "Arial", size: 22 } } },
    },
    sections: [
      {
        properties: {
          page: {
            size: { width: 11906, height: 16838 },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
          },
        },
        children,
      },
    ],
  });
  const blob = await Packer.toBlob(doc);
  return new Uint8Array(await blob.arrayBuffer());
}
