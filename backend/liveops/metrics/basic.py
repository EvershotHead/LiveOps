"""基础指标：主题占比、净支持率、争议度、趋势速度、互动影响、持续性。

全部由 Python 精确计算，LLM 不参与任何数值计算。
约定：所有比率指标输出 [0,1] 或 [-1,1]，无法计算时为 None（UI 显示"不可用"而非 0）。
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

STANCE_POLARIZED = ("支持", "反对", "中立", "混合")


@dataclass
class StanceDist:
    support: int = 0
    oppose: int = 0
    neutral: int = 0
    mixed: int = 0
    unclear: int = 0
    abstain: int = 0  # 未标注/弃权

    @property
    def total_stanced(self) -> int:
        return self.support + self.oppose + self.neutral + self.mixed

    @property
    def polarized(self) -> int:
        return self.support + self.oppose


def stance_dist(stances: list[str | None]) -> StanceDist:
    d = StanceDist()
    for s in stances:
        if s == "支持":
            d.support += 1
        elif s == "反对":
            d.oppose += 1
        elif s == "中立":
            d.neutral += 1
        elif s == "混合":
            d.mixed += 1
        elif s == "不明确":
            d.unclear += 1
        else:
            d.abstain += 1
    return d


def topic_share(topic_count: int, valid_total: int) -> float | None:
    if valid_total <= 0:
        return None
    return topic_count / valid_total


def net_support_rate(d: StanceDist) -> float | None:
    """(支持-反对)/(支持+反对)。同时展示中立/混合/不明确占比由 UI 负责。"""
    if d.polarized == 0:
        return None
    return (d.support - d.oppose) / d.polarized


def entropy_norm(d: StanceDist) -> float:
    """立场分布熵 / log(4)，归一到 [0,1]。无立场样本返回 0。"""
    total = d.total_stanced
    if total == 0:
        return 0.0
    h = 0.0
    for c in (d.support, d.oppose, d.neutral, d.mixed):
        if c > 0:
            p = c / total
            h -= p * math.log(p)
    return h / math.log(4)


def reply_conflict(edges: list[tuple[str, str]]) -> float | None:
    """楼中楼对立边占比：(父支持子反对) 或 (父反对子支持) / 全部已知立场边。"""
    known = [(a, b) for a, b in edges if a in ("支持", "反对") and b in ("支持", "反对")]
    if not known:
        return None
    conflict = sum(1 for a, b in known if a != b)
    return conflict / len(known)


def volume_norm(topic_count: int, study_total: int) -> float:
    if study_total <= 0:
        return 0.0
    return min(1.0, math.log1p(topic_count) / math.log1p(max(study_total, 1)))


def controversy_score(
    d: StanceDist,
    conflict: float | None,
    topic_count: int,
    study_total: int,
    *,
    w_entropy: float = 0.5,
    w_conflict: float = 0.3,
    w_volume: float = 0.2,
) -> float:
    """争议度 = 0.5*立场熵 + 0.3*回复冲突 + 0.2*log1p(讨论量)归一。"""
    c = conflict if conflict is not None else 0.0
    return w_entropy * entropy_norm(d) + w_conflict * c + w_volume * volume_norm(topic_count, study_total)


def trend_speed(daily_counts: list[int]) -> float | None:
    """相对时间每日新增数的线性回归斜率 / 全期均值（无量纲增速）。"""
    n = len(daily_counts)
    if n < 2:
        return None
    mean_y = sum(daily_counts) / n
    if mean_y == 0:
        return None
    mean_x = (n - 1) / 2
    num = sum((i - mean_x) * (y - mean_y) for i, y in enumerate(daily_counts))
    den = sum((i - mean_x) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    return slope / mean_y


def log_engagement_raw(likes: list[int], replies: list[int]) -> float:
    """mean(log1p(likes + replies))，未归一（跨主题归一在 composite 层做）。"""
    if not likes:
        return 0.0
    vals = [math.log1p(l + r) for l, r in zip(likes, replies)]
    return sum(vals) / len(vals)


def persistence(
    active_days: int, window_days: int, distinct_videos: int, total_videos: int
) -> float:
    """0.5*活跃天数占比 + 0.5*涉及视频占比。"""
    day_part = active_days / window_days if window_days > 0 else 0.0
    vid_part = distinct_videos / total_videos if total_videos > 0 else 0.0
    return 0.5 * min(day_part, 1.0) + 0.5 * min(vid_part, 1.0)


def ugc_diffusion(
    category_coverage: float,
    video_count_norm: float,
    growth: float,
    *,
    w_category: float = 0.4,
    w_videos: float = 0.3,
    w_growth: float = 0.3,
) -> float:
    """UGC 扩散：类目覆盖 + 视频数 + 讨论增长。播放量不直接等同口碑。"""
    return w_category * category_coverage + w_videos * video_count_norm + w_growth * max(0.0, min(1.0, growth))
