"""全量聚合：posts + annotations + videos → 指标 JSON（Python 计算，LLM 不参与）。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date
from typing import Any

from .. import config
from ..evidence import build_evidence_items, representative_evidence, to_jsonable
from ..normalize import day_offset, effective_posts
from ..schema import Annotation, CommunityPost, ContentItem, StudyConfig
from .basic import (
    controversy_score,
    log_engagement_raw,
    net_support_rate,
    persistence,
    reply_conflict,
    stance_dist,
    topic_share,
    trend_speed,
    ugc_diffusion,
    volume_norm,
)
from .composite import (
    issue_priority_scores,
    minmax_normalize,
    opportunity_scores,
    per_ten_videos,
    per_thousand,
    weight_sensitivity,
)


def _stance_of(a: Annotation) -> str | None:
    return a.stance.value if a.stance else None


def aggregate_metrics(
    study: StudyConfig,
    posts: list[CommunityPost],
    annotations: list[Annotation],
    videos: list[ContentItem],
    human_modified_ids: set[str] | None = None,
    weights: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """输出完整 metrics.json 结构（含分项、组合分、敏感性、证据索引、口径说明）。"""
    weights = weights or {
        "issue_priority": dict(config.ISSUE_PRIORITY_WEIGHTS),
        "opportunity": dict(config.OPPORTUNITY_WEIGHTS),
    }
    ann_by_id = {a.post_id: a for a in annotations}
    vid_by_id = {v.video_id: v for v in videos}
    eff = effective_posts(posts)

    # 有效样本 = effective 且 relevant=true
    relevant_posts = [p for p in eff if (a := ann_by_id.get(p.post_id)) and a.relevant is True]
    n_valid = len(relevant_posts)

    window_days = study.window.ferment[1] - study.window.preheat[0] + 1
    t0 = study.t0_date

    # 回复边（楼中楼）立场对
    edges: list[tuple[str, str]] = []
    post_by_id = {p.post_id: p for p in relevant_posts}
    for p in relevant_posts:
        if p.parent_id and p.parent_id in post_by_id:
            sa, sb = _stance_of(ann_by_id[p.post_id]), _stance_of(ann_by_id[p.parent_id])
            if sa and sb:
                edges.append((sa, sb))

    # 主题 → 样本集合
    topic_posts: dict[str, list[CommunityPost]] = defaultdict(list)
    for p in relevant_posts:
        a = ann_by_id[p.post_id]
        for t in a.topics:
            topic_posts[t].append(p)

    # 全局立场分布
    overall_dist = stance_dist(
        [_stance_of(ann_by_id[p.post_id]) for p in relevant_posts if ann_by_id.get(p.post_id)]
    )

    topic_stats: dict[str, dict[str, Any]] = {}
    for topic, tps in topic_posts.items():
        d = stance_dist([_stance_of(ann_by_id[p.post_id]) for p in tps])
        # 每日序列（相对天 -7..28）
        daily = [0] * window_days
        active_days = set()
        for p in tps:
            off = day_offset(t0, p.published_at.date())
            idx = off - study.window.preheat[0]
            if 0 <= idx < window_days:
                daily[idx] += 1
                active_days.add(off)
        likes = [p.likes for p in tps]
        replies = [p.reply_count for p in tps]
        vids = {p.video_id for p in tps}
        # 反对强度：反对占比 × 反对平均强度/3
        oppose_anns = [ann_by_id[p.post_id] for p in tps if ann_by_id[p.post_id].stance and ann_by_id[p.post_id].stance.value == "反对"]
        oppose_share = d.oppose / d.total_stanced if d.total_stanced else 0.0
        oppose_intensity = oppose_share * (
            (sum(a.intensity for a in oppose_anns) / len(oppose_anns) / 3) if oppose_anns else 0.0
        )
        support_rate = (d.support / d.polarized) if d.polarized else None
        # 视频类目覆盖
        cats = {vid_by_id[vid].category.value for vid in vids if vid in vid_by_id}
        # 增长：发酵期占比 - 上线期占比（简明可解释的增长代理）
        launch_n = sum(daily[(0 - study.window.preheat[0]):(8 - study.window.preheat[0])])
        ferment_n = sum(daily[(8 - study.window.preheat[0]):])
        growth_delta = (ferment_n - launch_n) / len(tps) if tps else 0.0

        topic_stats[topic] = {
            "count": len(tps),
            "topic_share": topic_share(len(tps), n_valid),
            "stance": asdict(d),
            "net_support_rate": net_support_rate(d),
            "support_rate": support_rate,
            "controversy": controversy_score(
                d, reply_conflict(edges), len(tps), max(n_valid, 1)
            ),
            "reply_conflict": reply_conflict(edges),
            "trend_speed": trend_speed(daily),
            "daily_counts": daily,
            "engagement_raw": log_engagement_raw(likes, replies),
            "video_count": len(vids),
            "video_categories": sorted(cats),
            "persistence": persistence(len(active_days), window_days, len(vids), max(len(videos), 1)),
            "ugc_diffusion": ugc_diffusion(
                len(cats) / 5, min(1.0, len(vids) / max(len(videos), 1)), growth_delta
            ),
            "oppose_intensity_raw": oppose_intensity,
            "growth_delta": growth_delta,
        }

    # 跨主题归一 → 组合分
    topics = list(topic_stats.keys())
    comp_rows_issue = {
        t: {
            "oppose_intensity": topic_stats[t]["oppose_intensity_raw"],
            "topic_share": topic_stats[t]["topic_share"] or 0.0,
            "growth": max(0.0, min(1.0, topic_stats[t]["growth_delta"] + 0.5)),  # 平移到 [0,1]
            "engagement": topic_stats[t]["engagement_raw"],
            "persistence": topic_stats[t]["persistence"],
        }
        for t in topics
    }
    comp_rows_opp = {
        t: {
            "support_rate": topic_stats[t]["support_rate"] or 0.0,
            "topic_growth": max(0.0, min(1.0, topic_stats[t]["growth_delta"] + 0.5)),
            "video_coverage": min(1.0, topic_stats[t]["video_count"] / max(len(videos), 1)),
            "engagement": topic_stats[t]["engagement_raw"],
            "persistence": topic_stats[t]["persistence"],
        }
        for t in topics
    }
    # 分项 min-max 归一（组合分在 [0,1] 可比）
    def _norm_rows(rows: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        keys = next(iter(rows.values()), {}).keys()
        out = {t: {} for t in rows}
        for k in keys:
            col = minmax_normalize({t: rows[t][k] for t in rows})
            for t in rows:
                out[t][k] = col[t]
        return out

    norm_issue = _norm_rows(comp_rows_issue) if topics else {}
    norm_opp = _norm_rows(comp_rows_opp) if topics else {}

    issue_scores = issue_priority_scores(norm_issue, weights["issue_priority"])
    opp_scores = opportunity_scores(norm_opp, weights["opportunity"])
    sens_issue = weight_sensitivity(norm_issue, weights["issue_priority"], "issue") if topics else None
    sens_opp = weight_sensitivity(norm_opp, weights["opportunity"], "opportunity") if topics else None

    # 证据
    evidence = build_evidence_items(relevant_posts, ann_by_id, vid_by_id,
                                    human_modified_ids=human_modified_ids or set())
    evidence_index = {
        t: representative_evidence(evidence, t) for t in topics
    }
    return {
        "study_id": study.study_id,
        "game": study.game.value,
        "version_label": study.version_label,
        "t0_date": study.t0_date.isoformat(),
        "scope_statement": "所采样的 B 站讨论（不代表所有玩家）",
        "dataset": {
            "total_posts": len(posts),
            "effective_posts": len(eff),
            "relevant_posts": n_valid,
            "videos": len(videos),
            "abstain_count": sum(1 for a in annotations if a.relevant is None),
            "irrelevant_count": sum(1 for a in annotations if a.relevant is False),
        },
        "overall": {
            "stance": asdict(overall_dist),
            "net_support_rate": net_support_rate(overall_dist),
        },
        "topics": topic_stats,
        "composites": {
            "issue_priority": {
                "weights": weights["issue_priority"],
                "scores": issue_scores,
                "components": norm_issue,
                "disclaimer": "可配置的运营排序规则，非客观事实",
            },
            "opportunity": {
                "weights": weights["opportunity"],
                "scores": opp_scores,
                "components": norm_opp,
                "disclaimer": "可配置的运营排序规则，非客观事实",
            },
            "sensitivity": {
                "issue": sens_issue.__dict__ if sens_issue else None,
                "opportunity": sens_opp.__dict__ if sens_opp else None,
            },
        },
        "per_thousand_basis": {
            "per_1000_comments": {t: per_thousand(topic_stats[t]["count"], n_valid) for t in topics},
            "per_10_videos": {t: per_ten_videos(topic_stats[t]["video_count"], len(videos)) for t in topics},
        },
        "evidence_index": evidence_index,
        "evidence_items": to_jsonable(evidence),
    }
