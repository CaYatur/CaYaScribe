import { useCallback, useEffect, useMemo, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { invoke } from "@tauri-apps/api/core";
import { api, setSidecar, sidecar, type AssetRow, type JobBody } from "./lib/api";
import { streamEvents } from "./lib/sse";
import { exportJson, exportSrt, exportTxt, exportVtt, type Segment, type Speaker } from "./lib/export";
import { formatBytes, formatClock } from "./lib/format";
import {
  assetLabel,
  detectLocale,
  messages,
  persistLocale,
  stageLabel,
  type Locale,
} from "./i18n";
import "./App.css";

type JobState = {
  stage: string;
  pct: number;
  error?: string;
};

export default function App() {
  const [locale, setLocale] = useState<Locale>(() => detectLocale());
  const t = messages(locale);
  const [ready, setReady] = useState(false);
  const [assets, setAssets] = useState<AssetRow[]>([]);
  const [showMissing, setShowMissing] = useState(false);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [mediaPath, setMediaPath] = useState("");
  const [speakerCount, setSpeakerCount] = useState("");
  const [language, setLanguage] = useState("auto");
  const [quality, setQuality] = useState<JobBody["quality"]>("balanced");
  const [enhance, setEnhance] = useState<JobBody["enhance"]>("auto");
  const [job, setJob] = useState<JobState | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameVal, setRenameVal] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  const [wantTs, setWantTs] = useState(true);
  const [wantSpk, setWantSpk] = useState(true);
  const [dl, setDl] = useState<{ assetId?: string; bytes: number; total: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showModels, setShowModels] = useState(false);

  function changeLocale(next: Locale) {
    setLocale(next);
    persistLocale(next);
    document.documentElement.lang = next;
  }

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const missing = useMemo(() => assets.filter((a) => !a.present), [assets]);
  const missingForQuality = useMemo(() => {
    return missing.filter(
      (a) => a.required || a.qualityTiers.includes(quality) || a.kind === "ffmpeg",
    );
  }, [missing, quality]);

  const qualityOptions: { id: JobBody["quality"]; label: string }[] = [
    { id: "fast", label: t.qualityFast },
    { id: "balanced", label: t.qualityBalanced },
    { id: "high", label: t.qualityHigh },
    { id: "max", label: t.qualityMax },
  ];

  const refreshAssets = useCallback(async () => {
    const data = await api.assets();
    setAssets(data.assets);
    const next: Record<string, boolean> = {};
    for (const a of data.assets) {
      if (!a.present && (a.required || a.id === "whisper-turbo-ct2" || a.kind === "diarization")) {
        next[a.id] = true;
      }
    }
    setPicked(next);
    if (data.assets.some((a) => !a.present && a.required)) setShowMissing(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const info = await invoke<{ port: number; token: string }>("sidecar_info");
        setSidecar(info);
      } catch {
        setSidecar({ port: 8765, token: "dev-token" });
      }
      for (let i = 0; i < 40 && !cancelled; i++) {
        try {
          await api.health();
          if (!cancelled) {
            setReady(true);
            await refreshAssets();
          }
          return;
        } catch {
          await new Promise((r) => setTimeout(r, 250));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshAssets]);

  async function pickFile() {
    try {
      const selected = await open({
        multiple: false,
        filters: [{ name: t.mediaFilter, extensions: ["mp3", "mp4", "wav", "m4a", "mkv", "webm", "flac", "ogg", "aac"] }],
      });
      if (typeof selected === "string") setMediaPath(selected);
    } catch {
      /* browser fallback below */
    }
  }

  async function startDownload() {
    const ids = Object.entries(picked).filter(([, v]) => v).map(([k]) => k);
    if (!ids.length) return;
    setErr(null);
    await api.download(ids);
    const timer = setInterval(async () => {
      const p = await api.assetProgress();
      setDl({ assetId: p.assetId ?? undefined, bytes: p.bytes, total: p.total });
      if (!p.active) {
        clearInterval(timer);
        setDl(null);
        await refreshAssets();
        if (!p.error) setShowMissing(false);
        if (p.error) setErr(p.error);
      }
    }, 400);
  }

  async function startJob() {
    setErr(null);
    if (!mediaPath) {
      setErr(t.pickFile);
      return;
    }
    const n = speakerCount.trim() === "" ? null : Number(speakerCount);
    const body: JobBody = {
      mediaPath,
      language,
      quality,
      speakerCount: n && Number.isFinite(n) ? n : null,
      enhance,
    };
    try {
      const { jobId: id } = await api.createJob(body);
      setJobId(id);
      setSegments([]);
      setSpeakers([]);
      setJob({ stage: "starting", pct: 1 });
      await streamEvents(api.jobUrl(id), sidecar().token, (event, data) => {
        const d = data as Record<string, unknown>;
        if (event === "progress") {
          setJob({ stage: String(d.stage ?? ""), pct: Number(d.pct ?? 0) });
        }
        if (event === "done") {
          setSegments((d.segments as Segment[]) || []);
          setSpeakers((d.speakers as Speaker[]) || []);
          setJob({ stage: "done", pct: 100 });
        }
        if (event === "error") {
          setJob({ stage: "error", pct: 0, error: String(d.error ?? "error") });
          setErr(String(d.error ?? "error"));
        }
      });
    } catch (e) {
      setErr(String(e));
    }
  }

  function applyRename() {
    if (!renameId) return;
    setSpeakers((prev) => prev.map((s) => (s.id === renameId ? { ...s, name: renameVal || s.id } : s)));
    setRenameId(null);
  }

  function speakerName(id: string) {
    return speakers.find((s) => s.id === id)?.name ?? id;
  }

  function downloadBlob(name: string, text: string) {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const opts = { timestamps: wantTs, speakers: wantSpk };
  const jobBusy = job !== null && job.stage !== "done" && job.stage !== "error";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>CaYaScribe</h1>
          <span>{t.subtitle}</span>
        </div>
        <div className="top-actions">
          <span className="offline">{ready ? t.connected : t.disconnected}</span>
          <label className="sr-only" htmlFor="ui-lang">{t.uiLanguage}</label>
          <select
            id="ui-lang"
            className="lang"
            value={locale}
            onChange={(e) => changeLocale(e.target.value === "tr" ? "tr" : "en")}
            title={t.uiLanguage}
          >
            <option value="en">English</option>
            <option value="tr">Türkçe</option>
          </select>
          <button className="btn ghost" onClick={() => setShowModels(true)}>{t.settings}</button>
        </div>
      </header>

      {showMissing && missing.length > 0 && (
        <div className="banner">
          <div>
            <h3>{t.missingTitle}</h3>
            <p>{t.missingBody}</p>
            <ul>
              {missing.map((a) => (
                <li key={a.id}>
                  <input
                    type="checkbox"
                    checked={!!picked[a.id]}
                    onChange={(e) => setPicked((p) => ({ ...p, [a.id]: e.target.checked }))}
                  />
                  <span>
                    {assetLabel(locale, a.id, a.displayName)} · {formatBytes(a.sizeBytes)} · {a.license}
                    {a.present ? " ✓" : ""}
                  </span>
                </li>
              ))}
            </ul>
            {dl && (
              <div className="progress">
                {dl.assetId} — {formatBytes(dl.bytes)} / {formatBytes(dl.total || 1)}
                <div className="bar">
                  <span style={{ width: `${Math.min(100, (dl.bytes / (dl.total || 1)) * 100)}%` }} />
                </div>
              </div>
            )}
          </div>
          <div className="row">
            <button className="btn" onClick={() => setShowMissing(false)}>{t.later}</button>
            <button className="btn primary" onClick={startDownload}>{t.download}</button>
          </div>
        </div>
      )}

      <div className="layout">
        <aside className="panel">
          <label className="field">
            {t.file}
            <div className="file-row">
              <input value={mediaPath} onChange={(e) => setMediaPath(e.target.value)} placeholder={t.filePlaceholder} />
              <button className="btn" onClick={pickFile}>{t.browse}</button>
            </div>
          </label>
          <input
            type="file"
            style={{ marginBottom: 12 }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f && "path" in f && typeof (f as File & { path?: string }).path === "string") {
                setMediaPath((f as File & { path: string }).path);
              }
            }}
          />
          <label className="field">
            {t.speakers}
            <input
              type="number"
              min={1}
              placeholder={t.speakersPlaceholder}
              value={speakerCount}
              onChange={(e) => setSpeakerCount(e.target.value)}
            />
          </label>
          <p className="hint">{t.speakersHint}</p>
          <label className="field">
            {t.transcriptionLanguage}
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="auto">{t.langAuto}</option>
              <option value="tr">Türkçe</option>
              <option value="en">English</option>
              <option value="de">Deutsch</option>
              <option value="fr">Français</option>
              <option value="es">Español</option>
              <option value="ar">العربية</option>
              <option value="zh">中文</option>
              <option value="ru">Русский</option>
              <option value="ja">日本語</option>
            </select>
          </label>
          <label className="field">
            {t.quality}
            <select value={quality} onChange={(e) => setQuality(e.target.value as JobBody["quality"])}>
              {qualityOptions.map((q) => (
                <option key={q.id} value={q.id}>{q.label}</option>
              ))}
            </select>
          </label>
          <label className="field">
            {t.enhance}
            <select value={enhance} onChange={(e) => setEnhance(e.target.value as JobBody["enhance"])}>
              <option value="off">{t.enhanceOff}</option>
              <option value="auto">{t.enhanceAuto}</option>
              <option value="on">{t.enhanceOn}</option>
            </select>
          </label>
          <div className="row">
            <button className="btn primary" disabled={!ready || jobBusy} onClick={startJob}>
              {t.start}
            </button>
            {jobId && jobBusy && (
              <button className="btn" onClick={() => jobId && api.cancelJob(jobId)}>{t.cancel}</button>
            )}
          </div>
          {job && (
            <div className="progress">
              {job.error ? job.error : `${stageLabel(locale, job.stage)} · %${job.pct}`}
              <div className="bar"><span style={{ width: `${job.pct}%` }} /></div>
            </div>
          )}
          {err && <p className="error">{err}</p>}
          {missingForQuality.length > 0 && (
            <p className="hint">{t.missingForQuality}</p>
          )}
        </aside>

        <main className="editor">
          {segments.length === 0 ? (
            <div className="empty">
              <h2>{t.emptyTitle}</h2>
              <p>{t.empty}</p>
            </div>
          ) : (
            <>
              <div className="row" style={{ marginBottom: 12 }}>
                {speakers.map((s) => (
                  <button
                    key={s.id}
                    className="btn"
                    onClick={() => {
                      setRenameId(s.id);
                      setRenameVal(s.name);
                    }}
                  >
                    {s.id} → {s.name}
                  </button>
                ))}
                <button className="btn primary" onClick={() => setExportOpen(true)}>{t.export}</button>
              </div>
              {segments.map((s) => (
                <div className="segment" key={s.id}>
                  <time>
                    {formatClock(s.startMs, "txt")}
                    <br />
                    {formatClock(s.endMs, "txt")}
                  </time>
                  <button
                    className="spk"
                    onClick={() => {
                      setRenameId(s.speakerId);
                      setRenameVal(speakerName(s.speakerId));
                    }}
                  >
                    {speakerName(s.speakerId)}
                  </button>
                  <textarea
                    value={s.text}
                    onChange={(e) =>
                      setSegments((prev) => prev.map((x) => (x.id === s.id ? { ...x, text: e.target.value } : x)))
                    }
                  />
                </div>
              ))}
            </>
          )}
        </main>
      </div>

      <footer className="status">
        <span>v0.1.0 · MIT · {t.footerModels}</span>
        <span>{assets.filter((a) => a.present).length}/{assets.length} {t.footerAssets}</span>
      </footer>

      {renameId && (
        <div className="modal-back" onClick={() => setRenameId(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{t.rename} ({renameId})</h3>
            <p className="hint">{t.renameHint}</p>
            <input value={renameVal} onChange={(e) => setRenameVal(e.target.value)} autoFocus />
            <div className="actions">
              <button className="btn" onClick={() => setRenameId(null)}>{t.dismiss}</button>
              <button className="btn primary" onClick={applyRename}>{t.save}</button>
            </div>
          </div>
        </div>
      )}

      {exportOpen && (
        <div className="modal-back" onClick={() => setExportOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{t.export}</h3>
            <label className="check">
              <input type="checkbox" checked={wantTs} onChange={(e) => setWantTs(e.target.checked)} />
              {t.timestamps}
            </label>
            <label className="check">
              <input type="checkbox" checked={wantSpk} onChange={(e) => setWantSpk(e.target.checked)} />
              {t.labels}
            </label>
            <div className="actions">
              <button className="btn" onClick={() => downloadBlob("transcript.txt", exportTxt(segments, speakers, opts))}>TXT</button>
              <button className="btn" onClick={() => downloadBlob("transcript.srt", exportSrt(segments, speakers, opts))}>SRT</button>
              <button className="btn" onClick={() => downloadBlob("transcript.vtt", exportVtt(segments, speakers, opts))}>VTT</button>
              <button className="btn" onClick={() => downloadBlob("transcript.json", exportJson(segments, speakers))}>JSON</button>
            </div>
          </div>
        </div>
      )}

      {showModels && (
        <div className="modal-back" onClick={() => setShowModels(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{t.settings}</h3>
            <ul>
              {assets.map((a) => (
                <li key={a.id}>
                  <label className="check">
                    <input
                      type="checkbox"
                      disabled={a.present}
                      checked={a.present || !!picked[a.id]}
                      onChange={(e) => setPicked((p) => ({ ...p, [a.id]: e.target.checked }))}
                    />
                    {assetLabel(locale, a.id, a.displayName)} — {a.present ? t.downloaded : formatBytes(a.sizeBytes)}
                  </label>
                </li>
              ))}
            </ul>
            <div className="actions">
              <button className="btn" onClick={() => setShowModels(false)}>{t.close}</button>
              <button className="btn primary" onClick={startDownload}>{t.download}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
