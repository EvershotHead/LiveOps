"""组合指标：运营问题优先级 / 正向机会值 / 权重敏感性 / 双游戏归一化对照。

组合分数是可配置的运营排序规则，不是客观事实；
所有调用方（API/UI/报告）必须同时输出分项与权重敏感性。
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config


def minmax_normalize(values: dict[str, float]) -> dict[str, float]:
    """跨主题 min-max 归一到 [0,1]；全同值时全部 0.5（中性，不制造虚假差异）。"""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-12:
        return {k: 0.5 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


DEFAULT_ISSUE_WEIGHTS = dict(config.ISSUE_PRIORITY_WEIGHTS)
DEFAULT_OPPORTUNITY_WEIGHTS = dict(config.OPPORTUNITY_WEIGHTS)


def composite_score(row: dict[str, float], weights: dict[str, float]) -> float:
    return sum(row.get(k, 0.0) * w for k, w in weights.items())


def issue_priority_scores(
    rows: dict[str, dict[str, float]],
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """rows: topic -> {oppose_intensity, topic_share, growth, engagement, persistence}"""
    w = weights or DEFAULT_ISSUE_WEIGHTS
    return {t: composite_score(r, w) for t, r in rows.items()}


def opportunity_scores(
    rows: dict[str, dict[str, float]],
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """rows: topic -> {support_rate, topic_growth, video_coverage, engagement, persistence}"""
    w = weights or DEFAULT_OPPORTUNITY_WEIGHTS
    return {t: composite_score(r, w) for t, r in rows.items()}


def rank_of(scores: dict[str, float]) -> dict[str, int]:
    order = sorted(scores, key=lambda k: -scores[k])
    return {t: i + 1 for i, t in enumerate(order)}


@dataclass
class SensitivityResult:
    base_ranks: dict[str, int]
    scenarios: list[dict]  # {name, weights, ranks, rank_shift: {topic: delta}}

    def max_rank_shift(self) -> int:
        return max(
            (abs(v) for s in self.scenarios for v in s["rank_shift"].values()), default=0
        )


def weight_sensitivity(
    rows: dict[str, dict[str, float]],
    base_weights: dict[str, float],
    kind: str,
    perturb: float = 0.10,
) -> SensitivityResult:
    """±10% 扰动每个权重（重归一化），输出排名变化。

    kind: "issue" | "opportunity"（选择打分函数）。
    """
    fn = issue_priority_scores if kind == "issue" else opportunity_scores
    base_scores = fn(rows, base_weights)
    base_ranks = rank_of(base_scores)
    scenarios: list[dict] = []

    for key in base_weights:
        for sign in (+1, -1):
            w = dict(base_weights)
            w[key] = w[key] * (1 + sign * perturb)
            total = sum(w.values())
            w = {k: v / total for k, v in w.items()}
            ranks = rank_of(fn(rows, w))
            scenarios.append({
                "name": f"{key} {'+' if sign > 0 else '-'}{int(perturb*100)}%",
                "weights": w,
                "ranks": ranks,
                "rank_shift": {t: ranks[t] - base_ranks[t] for t in base_ranks},
            })
    return SensitivityResult(base_ranks=base_ranks, scenarios=scenarios)


def per_thousand(topic_count: int, total_comments: int) -> float | None:
    """双游戏归一化：每千条评论指标。样本量不同时才需要。"""
    if total_comments <= 0:
        return None
    return topic_count * 1000.0 / total_comments


def per_ten_videos(video_count: int, total_videos: int) -> float | None:
    if total_videos <= 0:
        return None
    return video_count * 10.0 / total_videos
