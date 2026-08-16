"""配额校验器：样本冻结前的强制检查。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schema import CommunityPost, ContentItem, PostFlag, StudyConfig
from ..normalize import day_offset, effective_posts


@dataclass
class QuotaReport:
    ok: bool = True
    checks: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            self.ok = False

    def summary(self) -> str:
        return "\n".join(
            f"{'✅' if c['passed'] else '❌'} {c['name']}: {c['detail']}" for c in self.checks
        )


def validate_sample(posts: list[CommunityPost], videos: list[ContentItem],
                    study: StudyConfig, *, in_window_only: bool = True) -> QuotaReport:
    rep = QuotaReport()
    # 1. 视频数
    lo, hi = study.video_quota
    rep.add("视频数", lo <= len(videos) <= hi, f"{len(videos)}（要求 {lo}-{hi}）")
    # 2. 类别覆盖
    by_cat: dict[str, int] = {}
    for v in videos:
        by_cat[v.category.value] = by_cat.get(v.category.value, 0) + 1
    for cat in ("official", "guide", "review", "fanwork", "controversy"):
        n = by_cat.get(cat, 0)
        rep.add(f"类别[{cat}]", n >= study.min_videos_per_category,
                f"{n}（要求 ≥{study.min_videos_per_category}）")
    # 3. 有效评论数
    eff = effective_posts(posts)
    clo, chi = study.comment_quota
    rep.add("有效评论数", clo <= len(eff) <= chi, f"{len(eff)}（要求 {clo}-{chi}）")
    # 4. 单视频占比 ≤ 10%
    counts: dict[str, int] = {}
    for p in eff:
        counts[p.video_id] = counts.get(p.video_id, 0) + 1
    if eff:
        worst_vid, worst_n = max(counts.items(), key=lambda kv: kv[1])
        share = worst_n / len(eff)
        rep.add("单视频上限", share <= study.max_share_per_video + 1e-9,
                f"{worst_vid} 占 {share:.1%}（≤{study.max_share_per_video:.0%}）")
    # 5. 时间窗内占比 ≥95%（冻结数据的窗口纯度）
    if in_window_only and posts:
        in_w = sum(1 for p in posts if study.window.in_window(day_offset(study.t0_date, p.published_at.date())))
        ratio = in_w / len(posts)
        rep.add("时间窗纯度", ratio >= 0.95, f"窗内 {in_w}/{len(posts)} = {ratio:.1%}")
    # 6. 单作者上限（采样器执行，此处复核）
    per_user: dict[str, int] = {}
    for p in eff:
        per_user[p.anon_user_id] = per_user.get(p.anon_user_id, 0) + 1
    max_user = max(per_user.values()) if per_user else 0
    rep.add("单作者上限", max_user <= 10, f"最多 {max_user} 条/作者（≤10）")
    return rep
