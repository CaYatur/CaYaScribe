export type SidecarInfo = { port: number; token: string };

let info: SidecarInfo = { port: 8765, token: "dev-token" };

export function setSidecar(next: SidecarInfo) {
  info = next;
}

export function sidecar(): SidecarInfo {
  return info;
}

function url(path: string): string {
  return `http://127.0.0.1:${info.port}${path}`;
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${info.token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(url(path), { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => fetch(url("/v1/health")).then((r) => r.json()),
  assets: () => req<{ assets: AssetRow[]; missingRequired: AssetRow[]; diskTotal: number }>("/v1/assets"),
  devices: () => req<{ cuda: boolean; vramMb: number; ffmpegLgpl: boolean }>("/v1/devices"),
  download: (ids: string[]) =>
    req<{ started: string; queued: string[] }>("/v1/assets/download", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
  cancelDownload: () => req("/v1/assets/cancel", { method: "POST" }),
  removeAssets: (ids: string[]) =>
    req<{ removed: string[]; assets: AssetRow[]; diskTotal: number }>("/v1/assets/remove", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
  assetProgress: () =>
    req<{
      active: boolean;
      assetId: string | null;
      bytes: number;
      total: number;
      error: string | null;
      source: string | null;
    }>("/v1/assets/progress"),
  createJob: (body: JobBody) =>
    req<{ jobId: string }>("/v1/jobs", { method: "POST", body: JSON.stringify(body) }),
  cancelJob: (id: string) => req(`/v1/jobs/${id}/cancel`, { method: "POST" }),
  jobUrl: (id: string) => url(`/v1/jobs/${id}/events`),
  assetsEventsUrl: () => url("/v1/assets/events"),
};

export type AssetRow = {
  id: string;
  kind: string;
  displayName: string;
  qualityTiers: string[];
  required: boolean;
  recommended: boolean;
  license: string;
  sizeBytes: number;
  diskBytes: number;
  present: boolean;
  path: string;
  source: string;
  hfRepo?: string | null;
};

export type JobBody = {
  mediaPath: string;
  language: string;
  quality: "fast" | "balanced" | "high" | "max";
  speakerCount: number | null;
  enhance: "off" | "auto" | "on";
  asrId?: string | null;
  embedId?: string | null;
};
