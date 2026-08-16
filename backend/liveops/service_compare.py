"""双游戏对照：相同相对时间窗 + 归一化指标，不输出胜负结论。"""

from __future__ import annotations

from typing import Any

from .service_review import RunStore


def build_comparison(run_a: str, run_b: str, store: RunStore | None = None) -> dict[str, Any]:
    """A/B 两 run 的主题级归一化对照。

    归一化：每千条有效评论（per_1000）、每十个视频（per_10_videos）。
    结构：只并列展示差异 + 样本差异提示，禁止"谁更好"结论。
    """
    store = store or RunStore()
    out = {}
    for key, rid in (("a", run_a), ("b", run_b)):
        m = store.metrics(rid)
        if m is None:
            raise KeyError(f"run {rid} 无 metrics")
        out[key] = m
    a, b = out["a"], out["b"]

    topics = sorted(set(a.get("topics", {})) | set(b.get("topics", {})))
    rows = []
    for t in topics:
        ta = a["topics"].get(t)
        tb = b["topics"].get(t)
        row: dict[str, Any] = {"topic": t}
        for side, m, ts in (("a", a, ta), ("b", b, tb)):
            n_valid = m["dataset"]["relevant_posts"] or 1
            n_videos = m["dataset"]["videos"] or 1
            if ts:
                row[f"{side}_per_1000"] = round(ts["count"] * 1000 / n_valid, 1)
                row[f"{side}_share"] = ts["topic_share"]
                row[f"{side}_net_support"] = ts["net_support_rate"]
                row[f"{side}_controversy"] = ts["controversy"]
                row[f"{side}_per_10_videos"] = round(ts["video_count"] * 10 / n_videos, 1)
                row[f"{side}_trend"] = ts["trend_speed"]
                row[f"{side}_count"] = ts["count"]
            else:
                for f in ("per_1000", "share", "net_support", "controversy",
                          "per_10_videos", "trend", "count"):
                    row[f"{side}_{f}"] = None
        rows.append(row)

    da, db = a["dataset"], b["dataset"]
    sample_gap = abs(da["relevant_posts"] - db["relevant_posts"]) / max(
        da["relevant_posts"], db["relevant_posts"], 1)

    return {
        "a": {"run_id": run_a, "game": a["game"], "version": a["version_label"],
              "t0": a["t0_date"], "dataset": da},
        "b": {"run_id": run_b, "game": b["game"], "version": b["version_label"],
              "t0": b["t0_date"], "dataset": db},
        "windows_identical": (a["t0_date"] == b["t0_date"]),
        "same_relative_window": True,   # 两者均以各自 T0 归一化（T-7~T+28）
        "topic_rows": rows,
        "sample_difference_note": (
            f"样本量差异 {sample_gap:.0%}（A 有效 {da['relevant_posts']} 条/{da['videos']} 视频，"
            f"B 有效 {db['relevant_posts']} 条/{db['videos']} 视频），"
            "对照使用每千条评论/每十视频归一化指标；本页不构成任何胜负结论。"
        ),
        "disclaimer": "所采样的 B 站讨论口径下的结构差异对照，不代表所有玩家，不构成任何胜负结论。",
    }
