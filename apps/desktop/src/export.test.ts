import { localeFromNavigator } from "./i18n";
import { exportDocx, exportSrt, exportTxt, type Segment, type Speaker } from "./lib/export";

if (localeFromNavigator("tr") !== "tr") throw new Error("tr locale");
if (localeFromNavigator("tr-TR") !== "tr") throw new Error("tr-TR locale");
if (localeFromNavigator("en-US") !== "en") throw new Error("en locale");
if (localeFromNavigator("de-DE") !== "en") throw new Error("unsupported UI lang must be en");
if (localeFromNavigator("ja") !== "en") throw new Error("unsupported UI lang must be en");


const speakers: Speaker[] = [
  { id: "A", name: "Ali" },
  { id: "B", name: "Berna" },
];
const segs: Segment[] = [
  { id: "s0", speakerId: "A", startMs: 0, endMs: 1500, text: "merhaba" },
  { id: "s1", speakerId: "B", startMs: 3_661_000, endMs: 3_662_000, text: "alo" },
];

const txt = exportTxt(segs, speakers, { timestamps: true, speakers: true });
if (!txt.includes("[00:00.0 – 00:01.5] Ali: merhaba")) {
  throw new Error("txt format");
}

const srt = exportSrt(segs, speakers, { timestamps: true, speakers: true });
if (!srt.includes("01:01:01,000 --> 01:01:02,000")) {
  throw new Error("srt hour field");
}

const docx = await exportDocx(segs, speakers, { timestamps: true, speakers: true }, "kayit");
if (docx[0] !== 0x50 || docx[1] !== 0x4b) {
  throw new Error("docx is not a zip");
}

console.log("export tests ok");
