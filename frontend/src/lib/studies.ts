/**
 * Study 注册表：演示模式下的可切换分析单元（游戏 × 版本）。
 * 文件名约定：public-data/<kind>-<study_id>.json（compare 例外，见 compareKey）。
 */

export type StudyMeta = {
  id: string;              // study_id，如 "genshin-7.0"
  game: "genshin" | "wuthering_waves";
  gameShort: "genshin" | "wuwa";
  version: string;         // "7.0"
  label: string;           // "原神 7.0"
  codename?: string;       // 版本名
  t0: string;              // ISO 日期
  fermentNote?: string;    // 发酵期窗口说明（诚实口径）
};

export const STUDIES: StudyMeta[] = [
  {
    id: "genshin-7.0", game: "genshin", gameShort: "genshin", version: "7.0",
    label: "原神 7.0", codename: "无神怜爱的雪国", t0: "2026-08-12",
  },
  {
    id: "genshin-6.8", game: "genshin", gameShort: "genshin", version: "6.8",
    label: "原神 6.8", t0: "2026-07-01",
  },
  {
    id: "wuthering-3.6", game: "wuthering_waves", gameShort: "wuwa", version: "3.6",
    label: "鸣潮 3.6", codename: "蜃云灯影，凡尘剑心", t0: "2026-08-20",
    fermentNote: "采集日距 T0 仅 22 天，发酵期窗口截至采集日（未满 T+28）",
  },
  {
    id: "wuthering-3.5", game: "wuthering_waves", gameShort: "wuwa", version: "3.5",
    label: "鸣潮 3.5", t0: "2026-07-10",
  },
];

export const DEFAULT_STUDY = "genshin-7.0";

export function getStudy(id: string): StudyMeta | undefined {
  return STUDIES.find((s) => s.id === id);
}

/** 当前演示 study（localStorage 持久化）。 */
export function currentStudyId(): string {
  if (typeof window === "undefined") return DEFAULT_STUDY;
  const v = window.localStorage.getItem("liveops.demoStudy");
  return v && getStudy(v) ? v : DEFAULT_STUDY;
}

export function setStudyId(id: string) {
  window.localStorage.setItem("liveops.demoStudy", id);
}

/** 同游戏上一版本（用于环比 delta）。 */
export function previousStudyOf(id: string): StudyMeta | undefined {
  const s = getStudy(id);
  if (!s) return undefined;
  return STUDIES.find((x) => x.game === s.game && x.id !== s.id);
}

/** 对照页可选的版本对（同代对照）。 */
export const COMPARE_PAIRS = [
  { key: "genshin-7.0_vs_wuthering-3.6", label: "原神 7.0 vs 鸣潮 3.6", current: true },
  { key: "genshin-6.8_vs_wuthering-3.5", label: "原神 6.8 vs 鸣潮 3.5", current: false },
];

export function currentCompareKey(): string {
  if (typeof window === "undefined") return COMPARE_PAIRS[0].key;
  const v = window.localStorage.getItem("liveops.comparePair");
  return v && COMPARE_PAIRS.some((p) => p.key === v) ? v : COMPARE_PAIRS[0].key;
}

export function setCompareKey(key: string) {
  window.localStorage.setItem("liveops.comparePair", key);
}
