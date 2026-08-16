"use client";

/**
 * 数据层：local 模式走 FastAPI；demo 模式读静态 /public-data/*.json（无密钥只读）。
 * NEXT_PUBLIC_DEMO=1 构建时切换。
 */

import type {
  CompareData, ControversyRow, EvaluationData, EvidenceItem, Overview,
  ReviewItem, RunSummary, SensitivityData, TimelineData,
} from "./types";

export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO === "1";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export type Mode = { mode: "local" | "demo"; read_only: boolean };
export let currentRunId: string | null = null;

export function setRunContext(runId: string | null) {
  currentRunId = runId;
  if (typeof window !== "undefined") {
    if (runId) window.localStorage.setItem("liveops.run", runId);
    else window.localStorage.removeItem("liveops.run");
  }
}

export function getStoredRun(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("liveops.run");
}

/** 演示模式当前游戏（genshin | wuwa）。 */
export function demoGame(): "genshin" | "wuwa" {
  if (typeof window === "undefined") return "genshin";
  return window.localStorage.getItem("liveops.demoGame") === "wuwa" ? "wuwa" : "genshin";
}

export function setDemoGame(g: "genshin" | "wuwa") {
  window.localStorage.setItem("liveops.demoGame", g);
}

async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`API ${path}: ${r.status}`);
  return r.json() as Promise<T>;
}

async function demoGet<T>(name: string): Promise<T> {
  const r = await fetch(`public-data/${name}.json`);
  if (!r.ok) throw new Error(`demo data ${name}: ${r.status}`);
  return r.json() as Promise<T>;
}

function ctx(runId?: string | null): string {
  const rid = runId ?? currentRunId ?? getStoredRun();
  if (!rid) throw new Error("未选择分析任务");
  return rid;
}

export type MetricsLike = {
  topics: Record<string, never>;
  claims?: { claim_id: string; text: string; metric_ids: string[]; evidence_ids: string[] }[];
  verify_result?: { passed: boolean; violations: unknown[] };
};

export const data = {
  mode: (): Mode => (DEMO_MODE ? { mode: "demo", read_only: true } : { mode: "local", read_only: false }),
  runs: (): Promise<RunSummary[]> =>
    DEMO_MODE ? demoGet<RunSummary[]>("runs").catch(() => []) : apiGet<RunSummary[]>("/api/runs"),
  runDetail: (id: string): Promise<Record<string, unknown>> => apiGet(`/api/runs/${id}`),
  overview: (runId?: string): Promise<Overview> =>
    DEMO_MODE ? demoGet<Overview>(`overview-${demoGame()}`) : apiGet<Overview>(`/api/runs/${ctx(runId)}/overview`),
  metrics: (runId?: string): Promise<MetricsLike> =>
    DEMO_MODE ? demoGet<MetricsLike>(`metrics-${demoGame()}`) : apiGet<MetricsLike>(`/api/runs/${ctx(runId)}/metrics`),
  timeline: (runId?: string): Promise<TimelineData> =>
    DEMO_MODE ? demoGet<TimelineData>(`timeline-${demoGame()}`) : apiGet<TimelineData>(`/api/runs/${ctx(runId)}/timeline`),
  controversy: (runId?: string): Promise<{ rows: ControversyRow[]; scope_statement: string }> =>
    DEMO_MODE
      ? demoGet<{ rows: ControversyRow[]; scope_statement: string }>(`controversy-${demoGame()}`)
      : apiGet<{ rows: ControversyRow[]; scope_statement: string }>(`/api/runs/${ctx(runId)}/controversy`),
  sensitivity: (runId?: string): Promise<SensitivityData> =>
    DEMO_MODE ? demoGet<SensitivityData>(`sensitivity-${demoGame()}`) : apiGet<SensitivityData>(`/api/runs/${ctx(runId)}/sensitivity`),
  evaluation: (runId?: string): Promise<EvaluationData> =>
    DEMO_MODE ? demoGet<EvaluationData>(`evaluation-${demoGame()}`) : apiGet<EvaluationData>(`/api/runs/${ctx(runId)}/evaluation`),
  compare: (): Promise<CompareData> => demoGet<CompareData>("compare"),
  compareRuns: (a: string, b: string): Promise<CompareData> => apiGet<CompareData>(`/api/compare/${a}/${b}`),
  reviewQueue: (runId: string, limit = 50): Promise<{ count: number; items: ReviewItem[] }> =>
    apiGet(`/api/review/${runId}/queue?limit=${limit}`),
  evidence: (runId: string, id: string): Promise<EvidenceItem> =>
    DEMO_MODE ? demoGet<EvidenceItem>(`evidence/${id}`) : apiGet<EvidenceItem>(`/api/evidence/${runId}/${id}`),
  reportUrl: (runId?: string): string =>
    DEMO_MODE ? `public-data/report-${demoGame()}.html` : `${API_BASE}/api/runs/${ctx(runId)}/report`,
};
