import { useCallback, useEffect, useRef, useState } from "react";
import { open, save } from "@tauri-apps/plugin-dialog";
import { invoke } from "@tauri-apps/api/core";
import { api, setSidecar, sidecar, type AssetRow, type JobBody } from "./lib/api";
import { streamEvents } from "./lib/sse";
import { exportDocx, exportJson, exportSrt, exportTxt, exportVtt, type Segment, type Speaker } from "./lib/export";
import { formatBytes, formatClock } from "./lib/format";
import {
  assetHint,
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
  stagePct?: number;
  stageDone?: number;
  stageTotal?: number;
};

const EMBED_IDS = ["wespeaker-resnet293-lm", "eres2net-large", "titanet-large", "titanet-small"];
const QUALITY_ORDER: JobBody["quality"][] = ["fast", "balanced", "high", "max"];
const QUALITY_FALLBACK: JobBody["quality"][] = ["fast", "balanced", "high"];
const ASR_KEY = "cayascribe.asrId";
const EMBED_KEY = "cayascribe.embedId";

function readStored(key: string): string {
  try {
    return localStorage.getItem(key) || "";
  } catch {
    return "";
  }
}

function writeStored(key: string, value: string) {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

function preferAsrId(list: AssetRow[], current: string): string {
  if (current && list.some((a) => a.id === current && a.kind === "asr" && a.present)) return current;
  const present = list.filter((a) => a.kind === "asr" && a.present);
  return present.find((a) => a.recommended)?.id || present[0]?.id || "";
}

function qualityTiersFor(row: AssetRow | undefined): JobBody["quality"][] {
  const raw = (row?.qualityTiers || []).filter((q): q is JobBody["quality"] =>
    QUALITY_ORDER.includes(q as JobBody["quality"]),
  );
  if (raw.length) return QUALITY_ORDER.filter((q) => raw.includes(q));
  return QUALITY_FALLBACK;
}

function clampQuality(row: AssetRow | undefined, current: JobBody["quality"]): JobBody["quality"] {
  const tiers = qualityTiersFor(row);
  return tiers.includes(current) ? current : (tiers[tiers.length - 1] ?? current);
}

export default function App() {
  const [locale, setLocale] = useState<Locale>(() => detectLocale());
  const t = messages(locale);
  const [ready, setReady] = useState(false);
  const [assets, setAssets] = useState<AssetRow[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [mediaPath, setMediaPath] = useState("");
  const [speakerCount, setSpeakerCount] = useState("");
  const [language, setLanguage] = useState("auto");
  const [quality, setQuality] = useState<JobBody["quality"]>("balanced");
  const [asrId, setAsrId] = useState(() => readStored(ASR_KEY));
  const [embedId, setEmbedId] = useState(() => readStored(EMBED_KEY));
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
  const [dl, setDl] = useState<{ assetId?: string; bytes: number; total: number; source?: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showModels, setShowModels] = useState(false);
  const [removeId, setRemoveId] = useState<string | null>(null);
  const jobAbort = useRef<AbortController | null>(null);
  const jobIdRef = useRef<string | null>(null);
  const jobLive = useRef(false);

  function changeLocale(next: Locale) {
    setLocale(next);
    persistLocale(next);
    document.documentElement.lang = next;
  }

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    const row = assets.find((a) => a.id === asrId);
    const tiers = qualityTiersFor(row);
    if (!tiers.length) return;
    setQuality((cur) => (tiers.includes(cur) ? cur : tiers[tiers.length - 1]));
  }, [asrId, assets]);

  const ffmpegOk = assets.some((a) => a.kind === "ffmpeg" && a.present);
  const asrAll = assets.filter((a) => a.kind === "asr");
  const asrPresent = asrAll.filter((a) => a.present);
  const selectedAsr = asrAll.find((a) => a.id === asrId);
  const qualityIds = qualityTiersFor(selectedAsr);
  const qualityLabels: Record<JobBody["quality"], string> = {
    fast: t.qualityFast,
    balanced: t.qualityBalanced,
    high: t.qualityHigh,
    max: t.qualityMax,
  };
  const qualityOptions = qualityIds.map((id) => ({ id, label: qualityLabels[id] }));
  const qualityValue = qualityOptions.some((q) => q.id === quality)
    ? quality
    : (qualityOptions[qualityOptions.length - 1]?.id ?? quality);
  const embedPresent = assets.filter((a) => a.kind === "diarization" && a.present && EMBED_IDS.includes(a.id));
  const asrPickedOk = Boolean(asrId) && asrPresent.some((a) => a.id === asrId);
  const canStartModels = ffmpegOk && asrPickedOk;

  function pickAsr(id: string) {
    setAsrId(id);
    writeStored(ASR_KEY, id);
    const row = asrAll.find((a) => a.id === id);
    setQuality((cur) => clampQuality(row, cur));
  }

  function pickEmbed(id: string) {
    setEmbedId(id);
    writeStored(EMBED_KEY, id);
  }

  const refreshAssets = useCallback(async () => {
    const data = await api.assets();
    setAssets(data.assets);
    const next: Record<string, boolean> = {};
    for (const a of data.assets) {
      if (!a.present && a.recommended) next[a.id] = true;
    }
    setPicked(next);
    if (data.assets.some((a) => !a.present && a.recommended)) setShowModels(true);
    setAsrId((cur) => {
      const nextId = preferAsrId(data.assets, cur);
      writeStored(ASR_KEY, nextId);
      return nextId;
    });
    setEmbedId((cur) => {
      const keep = cur && data.assets.some((a) => a.id === cur && a.present);
      const nextId = keep ? cur : "";
      writeStored(EMBED_KEY, nextId);
      return nextId;
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const info = await invoke<{ port: number; token: string; error?: string | null }>("sidecar_info");
        setSidecar(info);
        if (info.error) {
          if (!cancelled) setErr(`${t.sidecarFailed} ${info.error}`);
          return;
        }
      } catch {
        setSidecar({ port: 8765, token: "dev-token" });
      }
      for (let i = 0; i < 80 && !cancelled; i++) {
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
      if (!cancelled) setErr(t.sidecarFailed);
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

  async function confirmRemove() {
    if (!removeId || dl) return;
    if (job !== null && job.stage !== "done" && job.stage !== "error") return;
    setErr(null);
    try {
      await api.removeAssets([removeId]);
      setRemoveId(null);
      await refreshAssets();
    } catch (e) {
      setErr(String(e));
    }
  }

  function diskLabel(a: AssetRow): string {
    if (a.present) return `${t.downloaded} · ${formatBytes(a.diskBytes || 0)} ${t.onDisk}`;
    if ((a.diskBytes || 0) > 0) return `${t.incomplete} · ${formatBytes(a.diskBytes)} ${t.onDisk}`;
    return formatBytes(a.sizeBytes);
  }

  async function startDownload() {
    if (dl) return;
    const ids = assets.filter((a) => !a.present && picked[a.id]).map((a) => a.id);
    if (!ids.length) return;
    setErr(null);
    setDl({ assetId: ids[0], bytes: 0, total: 1 });
    try {
      await api.download(ids);
    } catch (e) {
      setDl(null);
      setErr(String(e));
      return;
    }
    const timer = setInterval(async () => {
      const p = await api.assetProgress();
      setDl({
        assetId: p.assetId ?? undefined,
        bytes: p.bytes,
        total: p.total,
        source: p.source ?? undefined,
      });
      if (!p.active) {
        clearInterval(timer);
        setDl(null);
        await refreshAssets();
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
      quality: qualityValue,
      speakerCount: n && Number.isFinite(n) ? n : null,
      enhance,
      asrId: asrId || null,
      embedId: embedId || null,
    };
    jobAbort.current?.abort();
    const ac = new AbortController();
    jobAbort.current = ac;
    try {
      const { jobId: id } = await api.createJob(body);
      jobIdRef.current = id;
      jobLive.current = true;
      setJobId(id);
      setSegments([]);
      setSpeakers([]);
      setJob({ stage: "starting", pct: 1 });
      await streamEvents(
        api.jobUrl(id),
        sidecar().token,
        (event, data) => {
          if (!jobLive.current || ac.signal.aborted) return;
          const d = data as Record<string, unknown>;
          if (event === "progress") {
            const stageDone = d.stageDone != null ? Number(d.stageDone) : undefined;
            const stageTotal = d.stageTotal != null ? Number(d.stageTotal) : undefined;
            const stagePct = d.stagePct != null ? Number(d.stagePct) : undefined;
            setJob({
              stage: String(d.stage ?? ""),
              pct: Number(d.pct ?? 0),
              stagePct: Number.isFinite(stagePct) ? stagePct : undefined,
              stageDone: Number.isFinite(stageDone) ? stageDone : undefined,
              stageTotal: Number.isFinite(stageTotal) ? stageTotal : undefined,
            });
          }
          if (event === "done") {
            setSegments((d.segments as Segment[]) || []);
            setSpeakers((d.speakers as Speaker[]) || []);
            setJob({ stage: "done", pct: 100 });
          }
          if (event === "cancelled") {
            jobLive.current = false;
            jobIdRef.current = null;
            setJob(null);
            setJobId(null);
          }
          if (event === "error") {
            setJob({ stage: "error", pct: 0, error: String(d.error ?? "error") });
            setErr(String(d.error ?? "error"));
          }
        },
        ac.signal,
      );
    } catch (e) {
      const name = e instanceof Error ? e.name : "";
      if (name === "AbortError") return;
      if (!jobLive.current) return;
      setErr(String(e));
    }
  }

  async function cancelRunningJob() {
    const id = jobIdRef.current ?? jobId;
    jobLive.current = false;
    jobAbort.current?.abort();
    jobAbort.current = null;
    jobIdRef.current = null;
    setJob(null);
    setJobId(null);
    if (!id) return;
    try {
      await api.cancelJob(id);
    } catch {
      /* already gone */
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

  function transcriptStem(): string {
    const raw = mediaPath.split(/[/\\]/).pop() || "transcript";
    const stem = raw.replace(/\.[^.]+$/, "");
    return stem || "transcript";
  }

  async function exportAs(kind: "txt" | "srt" | "vtt" | "json" | "docx") {
    const stem = transcriptStem();
    const name = `${stem}.${kind}`;
    try {
      const path = await save({
        defaultPath: name,
        filters: [{ name: kind === "docx" ? "Word" : kind.toUpperCase(), extensions: [kind] }],
      });
      if (!path) return;
      if (kind === "docx") {
        const bytes = await exportDocx(segments, speakers, opts, stem);
        await invoke("save_bytes_file", { path, contents: Array.from(bytes) });
      } else {
        const text =
          kind === "txt"
            ? exportTxt(segments, speakers, opts)
            : kind === "srt"
              ? exportSrt(segments, speakers, opts)
              : kind === "vtt"
                ? exportVtt(segments, speakers, opts)
                : exportJson(segments, speakers);
        await invoke("save_text_file", { path, contents: text });
      }
      setExportOpen(false);
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }

  const opts = { timestamps: wantTs, speakers: wantSpk };
  const jobBusy = job !== null && job.stage !== "done" && job.stage !== "error";
  const downloading = Boolean(dl);
  const hasQueuedDownloads = assets.some((a) => !a.present && !!picked[a.id]);
  const canStartDownload = hasQueuedDownloads && !downloading;
  const diskTotal = assets.reduce((n, a) => n + (a.diskBytes || 0), 0);
  const removeTarget = assets.find((a) => a.id === removeId);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <svg className="brand-logo" viewBox="0 0 188 28" aria-label="CaYaScribe" role="img">
            <text x="0" y="22" fontFamily="Inter, Segoe UI, sans-serif" fontSize="22" fontWeight="700" letterSpacing="-0.045em">
              <tspan fill="#dc2626">CaYa</tspan>
              <tspan fill="#f8fafc">Scribe</tspan>
            </text>
          </svg>
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

      <div className="layout">
        <aside className="panel">
          <label className="field">
            {t.file}
            <button className="btn" onClick={pickFile}>{t.browse}</button>
            <span className="file-name">{mediaPath ? mediaPath.split(/[/\\]/).pop() : t.noFile}</span>
          </label>
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
            {t.asrModel}
            <select
              value={asrId}
              onChange={(e) => {
                const next = e.target.value;
                const row = asrAll.find((a) => a.id === next);
                if (row && !row.present) {
                  setShowModels(true);
                  return;
                }
                pickAsr(next);
              }}
            >
              {asrAll.length === 0 && <option value="">{t.noFile}</option>}
              {asrAll.map((a) => (
                <option key={a.id} value={a.id} disabled={!a.present}>
                  {assetLabel(locale, a.id, a.displayName)}
                  {a.recommended ? ` · ${t.recommended}` : ""}
                  {a.present ? "" : ` (${t.qualityLocked})`}
                </option>
              ))}
            </select>
          </label>
          <p className="hint">{t.asrModelHint}</p>
          <label className="field">
            {t.quality}
            <select
              value={qualityValue}
              disabled={!asrPickedOk || qualityOptions.length === 0}
              onChange={(e) => setQuality(e.target.value as JobBody["quality"])}
            >
              {qualityOptions.map((q) => (
                <option key={q.id} value={q.id}>
                  {q.label}
                </option>
              ))}
            </select>
          </label>
          <p className="hint">{t.qualityHint}</p>
          {embedPresent.length > 0 && (
            <label className="field">
              {t.embedModel}
              <select value={embedId} onChange={(e) => pickEmbed(e.target.value)}>
                <option value="">{t.embedModelAuto}</option>
                {embedPresent.map((a) => (
                  <option key={a.id} value={a.id}>
                    {assetLabel(locale, a.id, a.displayName)}
                    {a.recommended ? ` · ${t.recommended}` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="field">
            {t.enhance}
            <select value={enhance} onChange={(e) => setEnhance(e.target.value as JobBody["enhance"])}>
              <option value="off">{t.enhanceOff}</option>
              <option value="auto">{t.enhanceAuto}</option>
              <option value="on">{t.enhanceOn}</option>
            </select>
          </label>
          <div className="panel-actions">
            {!canStartModels && (
              <p className="hint start-hint">
                {asrPresent.length > 0 ? t.pickDownloadedModel : t.startNeedsModels}
              </p>
            )}
            <div className="row">
              <button className="btn primary" disabled={!ready || jobBusy || !mediaPath || !canStartModels} onClick={startJob}>
                {t.start}
              </button>
              {!canStartModels && (
                <button className="btn" onClick={() => setShowModels(true)}>{t.settings}</button>
              )}
              {jobBusy && (
                <button className="btn" type="button" onClick={() => void cancelRunningJob()}>{t.cancel}</button>
              )}
            </div>
            {job && (
              <div className="progress">
                {job.error ? job.error : `${t.stageOverall} · ${stageLabel(locale, job.stage)} · %${job.pct}`}
                <div className="bar"><span style={{ width: `${job.pct}%` }} /></div>
                {!job.error && job.stagePct != null && (
                  <>
                    <p className="stage-line">
                      {t.stageCurrent} · {stageLabel(locale, job.stage)}
                      {job.stageTotal ? ` · ${job.stageDone ?? 0}/${job.stageTotal}` : ""}
                      {` · %${job.stagePct}`}
                    </p>
                    <div className="bar stage"><span style={{ width: `${job.stagePct}%` }} /></div>
                  </>
                )}
              </div>
            )}
            {err && <p className="error">{err}</p>}
          </div>
        </aside>

        <main className={`editor${jobBusy ? " is-working" : segments.length === 0 ? " is-idle" : ""}`}>
          {segments.length > 0 ? (
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
          ) : jobBusy && job ? (
            <div className="working" aria-live="polite">
              <div className="working-visual" aria-hidden="true">
                <div className="working-rings">
                  <span />
                  <span />
                  <span />
                </div>
                <div className="eq">
                  <span /><span /><span /><span /><span /><span /><span />
                </div>
              </div>
              <h2>{stageLabel(locale, job.stage)}</h2>
              <p>{t.workingBody}</p>
              {mediaPath && (
                <p className="working-file">{mediaPath.split(/[/\\]/).pop()}</p>
              )}
              <div className="working-meters">
                <div className="working-meter">
                  <p className="working-pct">{t.stageOverall} · %{job.pct}</p>
                  <div className="working-bar">
                    <span style={{ width: `${Math.max(4, job.pct)}%` }} />
                  </div>
                </div>
                {job.stagePct != null && (
                  <div className="working-meter">
                    <p className="working-pct">
                      {t.stageCurrent} · {stageLabel(locale, job.stage)}
                      {job.stageTotal ? ` · ${job.stageDone ?? 0}/${job.stageTotal}` : ""}
                      {` · %${job.stagePct}`}
                    </p>
                    <div className="working-bar stage">
                      <span style={{ width: `${Math.max(4, job.stagePct)}%` }} />
                    </div>
                  </div>
                )}
              </div>
              <button className="btn working-cancel" type="button" onClick={() => void cancelRunningJob()}>
                {t.cancel}
              </button>
            </div>
          ) : (
            <div className="empty idle">
              <div className="idle-scene" aria-hidden="true">
                <div className="idle-mic">
                  <div className="idle-rings">
                    <span />
                    <span />
                    <span />
                  </div>
                  <svg className="idle-mic-icon" viewBox="0 0 48 48">
                    <rect x="18" y="8" width="12" height="20" rx="6" fill="#f8fafc" />
                    <path d="M14 24a10 10 0 0 0 20 0" fill="none" stroke="#dc2626" strokeWidth="2.5" strokeLinecap="round" />
                    <path d="M24 34v6M17 40h14" stroke="#dc2626" strokeWidth="2.5" strokeLinecap="round" />
                  </svg>
                </div>
                <div className="idle-stream">
                  <span />
                  <span />
                  <span />
                  <span />
                </div>
                <div className="idle-col">
                  <div className="idle-page">
                    <div className="idle-lines">
                      <i />
                      <i />
                      <i />
                    </div>
                    <span className="idle-pen" />
                    <p className="idle-type">{t.idleType}</p>
                  </div>
                  <div className="idle-words">
                    <span>{t.idleSpeak}</span>
                    <span>{t.idleWrite}</span>
                  </div>
                </div>
              </div>
              <h2>{t.emptyTitle}</h2>
              <p>{t.empty}</p>
            </div>
          )}
        </main>
      </div>

      <footer className="status">
        <span>v0.1.3 · MIT · {t.footerModels}</span>
        <span>{formatBytes(diskTotal)} {t.onDisk} · {assets.filter((a) => a.present).length}/{assets.length} {t.footerAssets}</span>
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
            <p className="hint">{t.exportHint}</p>
            <label className="check">
              <input type="checkbox" checked={wantTs} onChange={(e) => setWantTs(e.target.checked)} />
              {t.timestamps}
            </label>
            <label className="check">
              <input type="checkbox" checked={wantSpk} onChange={(e) => setWantSpk(e.target.checked)} />
              {t.labels}
            </label>
            <div className="actions">
              <button className="btn" onClick={() => void exportAs("txt")}>TXT</button>
              <button className="btn" onClick={() => void exportAs("srt")}>SRT</button>
              <button className="btn" onClick={() => void exportAs("vtt")}>VTT</button>
              <button className="btn" onClick={() => void exportAs("json")}>JSON</button>
              <button className="btn" onClick={() => void exportAs("docx")}>Word</button>
            </div>
          </div>
        </div>
      )}

      {showModels && (
        <div className="modal-back" onClick={() => { if (!dl) setShowModels(false); }}>
          <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
            <h3>{t.missingTitle}</h3>
            <p className="modal-lead">{t.missingBody}</p>
            <ul className="model-list">
              {assets.map((a) => (
                <li key={a.id} className="model-row">
                  <label className="check">
                    <input
                      type="checkbox"
                      disabled={a.present}
                      checked={a.present || !!picked[a.id]}
                      onChange={(e) => setPicked((p) => ({ ...p, [a.id]: e.target.checked }))}
                    />
                    <span>
                      {a.recommended && <em className="badge">{t.recommended}</em>}
                      {(a.id === "whisper-large-v3-tr" || a.id === "whisper-large-v3-ct2") && (
                        <em className="badge hard">{t.hardAudio}</em>
                      )}
                      {assetLabel(locale, a.id, a.displayName)}
                      {assetHint(locale, a.id) && (
                        <small className="model-hint">{assetHint(locale, a.id)}</small>
                      )}
                      <small className="src">
                        {t.source}: {a.source} · {diskLabel(a)}
                      </small>
                    </span>
                  </label>
                  {(a.present || (a.diskBytes || 0) > 0) && (
                    <button
                      className="btn danger"
                      disabled={downloading || jobBusy}
                      onClick={() => setRemoveId(a.id)}
                    >
                      {t.remove}
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {dl && (
              <div className="progress">
                {dl.assetId} {dl.source ? `· ${dl.source}` : ""} — {formatBytes(dl.bytes)} / {formatBytes(dl.total || 1)}
                <div className="bar">
                  <span style={{ width: `${Math.min(100, (dl.bytes / (dl.total || 1)) * 100)}%` }} />
                </div>
              </div>
            )}
            {removeId && removeTarget && (
              <div className="remove-confirm">
                <p>{t.removeConfirm}</p>
                <p className="hint">
                  {assetLabel(locale, removeTarget.id, removeTarget.displayName)} · {formatBytes(removeTarget.diskBytes || 0)} {t.onDisk}
                </p>
                <div className="row">
                  <button className="btn" onClick={() => setRemoveId(null)}>{t.dismiss}</button>
                  <button className="btn danger" disabled={downloading || jobBusy} onClick={() => void confirmRemove()}>
                    {t.remove}
                  </button>
                </div>
              </div>
            )}
            <div className="actions">
              <button className="btn" onClick={() => setShowModels(false)}>{t.close}</button>
              <button
                className={`btn primary${downloading ? " downloading" : ""}`}
                disabled={!canStartDownload && !downloading}
                aria-busy={downloading}
                onClick={() => { if (canStartDownload) void startDownload(); }}
              >
                {downloading ? (
                  <span className="downloading-label">
                    <span className="btn-spinner" aria-hidden="true" />
                    {t.downloading}
                  </span>
                ) : (
                  t.download
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
