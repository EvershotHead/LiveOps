"""分析节点：受约束状态图的各阶段实现（纯函数，state dict 进出）。

流程：normalize → relevance_filter(规则) → embed_cluster(主题先验+新兴候选)
     → annotate_cheap(LLM) → route_review → annotate_strong(复核)
     → [await_human] → aggregate(Python) → report(程序化结论) → verify(规则)
"""

from __future__ import annotations

import random
from typing import Any, Callable

from ..cluster import assign_topics, compute_topic_centroids
from ..config import (
    ANALYSIS_TEXT_WINDOW,
    EMBED_COSINE_ASSIGN_THRESHOLD,
    MIN_NEW_TOPIC_CLUSTER_SIZE,
    ROUTE_REVIEW_LIKE_PERCENTILE,
    ROUTE_REVIEW_MIN_CONFIDENCE,
)
from ..embed import embed_texts
from ..evidence import build_evidence_items, representative_evidence
from ..llm import AbstainError, BaseLLMClient, RateLimitedError
from ..llm.prompts import v1
from ..llm.tasks import AnnotateOut, to_annotation_fields
from ..metrics.aggregate import aggregate_metrics
from ..normalize import effective_posts, normalize_posts
from ..report.verify import Claim, verify_claims
from ..schema import (
    Annotation,
    AnnotateStage,
    CommunityPost,
    ContentItem,
    StudyConfig,
)

STAGES = [
    "normalize",
    "relevance_filter",
    "embed_cluster",
    "annotate_cheap",
    "route_review",
    "annotate_strong",
    "await_human",
    "aggregate",
    "report",
    "verify",
]


# ---------- 1. 规范化 ----------

def node_normalize(state: dict) -> dict:
    study = StudyConfig.model_validate(state["study"])
    posts = [CommunityPost.model_validate(p) for p in state["posts"]]
    kept, report = normalize_posts(posts, study)
    return {
        "posts": [p.model_dump(mode="json") for p in kept],
        "normalize_report": {
            "total_in": report.total_in, "kept": report.kept,
            "dropped_out_of_window": report.dropped_out_of_window,
            "dropped_spam": report.dropped_spam,
            "duplicates_flagged": report.duplicates_flagged,
            "duplicate_groups": report.duplicate_groups,
            "warnings": report.warnings,
        },
    }


# ---------- 2. 相关性规则预筛 ----------

_OFFTOPIC_RE = None


def _offtopic_pattern():
    global _OFFTOPIC_RE
    import re
    if _OFFTOPIC_RE is None:
        # 明显其他游戏/纯交易：进 LLM 前的规则层（最终相关性由 LLM+人工判定）
        _OFFTOPIC_RE = re.compile(r"(出售账号|收售|出号|换绑|租号)")
    return _OFFTOPIC_RE


def node_relevance_filter(state: dict) -> dict:
    posts = [CommunityPost.model_validate(p) for p in state["posts"]]
    candidates, rule_excluded = [], 0
    for p in posts:
        if _offtopic_pattern().search(p.text):
            rule_excluded += 1
        else:
            candidates.append(p)
    return {
        "candidate_post_ids": [p.post_id for p in candidates],
        "relevance_report": {"rule_excluded": rule_excluded, "candidates": len(candidates)},
    }


# ---------- 3. 嵌入 + 主题先验 + 新兴主题候选 ----------

def node_embed_cluster(state: dict) -> dict:
    posts = [CommunityPost.model_validate(p) for p in state["posts"]]
    cand = set(state.get("candidate_post_ids") or [p.post_id for p in posts])
    sel = [p for p in posts if p.post_id in cand]

    def embed_fn(texts):
        return embed_texts(texts).vectors

    centroids = compute_topic_centroids(embed_fn)
    res = embed_texts([p.text for p in sel])
    cluster = assign_topics(
        [p.post_id for p in sel],
        [p.text for p in sel],
        res.vectors,
        centroids,
        threshold=EMBED_COSINE_ASSIGN_THRESHOLD,
        min_cluster_size=MIN_NEW_TOPIC_CLUSTER_SIZE,
    )
    return {
        "topic_priors": {pid: a.topics for pid, a in cluster.assignments.items()},
        "new_topic_candidates": cluster.new_topic_candidates,
        "embed_quality": res.embed_quality,
        "embed_model": res.model_name,
    }


# ---------- 4. 低成本模型结构化标注 ----------

def _annotate_posts(posts, priors, videos_by_id, llm, stage, study) -> list[dict]:
    out: list[dict] = []
    for p in posts:
        prior = priors.get(p.post_id) or []
        video_title = videos_by_id.get(p.video_id, ContentItem(
            video_id=p.video_id, title=p.video_id, url=p.source_url,
            published_at=p.published_at, category="review")).title
        text_window = p.text[:ANALYSIS_TEXT_WINDOW]
        msgs = v1.build_annotate_messages(p.post_id, video_title, text_window)
        if prior:
            msgs[1]["content"] += f"\n\n## 语义匹配主题先验（仅供参考，可不同意）\n{prior}"
        try:
            r = llm.complete_json(msgs, AnnotateOut, prompt_version=v1.ANNOTATE_VERSION)
            fields = to_annotation_fields(r.value)
        except AbstainError as e:
            fields = {
                "relevant": None, "topics": [], "stance": None, "emotion": None,
                "intensity": 0, "irony": "无法判断", "intent": None, "issue_type": None,
                "confidence": 0.0, "evidence_span": "", "abstain_reason": str(e)[:120],
            }
        fields.update({
            "post_id": p.post_id, "run_id": study.study_id,
            "model": llm.name, "prompt_version": v1.ANNOTATE_VERSION,
            "stage": stage.value,
        })
        out.append(fields)
    return out


def node_annotate_cheap(state: dict, llm: BaseLLMClient) -> dict:
    study = StudyConfig.model_validate(state["study"])
    posts = [CommunityPost.model_validate(p) for p in state["posts"]]
    cand = set(state.get("candidate_post_ids") or [])
    sel = [p for p in posts if not cand or p.post_id in cand]
    videos_by_id = {v["video_id"]: ContentItem.model_validate(v) for v in state.get("videos", [])}
    priors = state.get("topic_priors") or {}
    anns = _annotate_posts(sel, priors, videos_by_id, llm, AnnotateStage.CHEAP, study)
    return {"annotations": anns}


# ---------- 5. 复核路由 ----------

def route_review(post_ids, annotations: dict[str, Annotation],
                 likes_by_id, controversy_top_topics, topics_by_id,
                 *, audit_ratio: float = 0.05, seed: int = 7) -> list[str]:
    """路由规则（命中任一 → 强模型复核）：
    1. confidence < 0.60；2. irony ∈ {明显, 无法判断}；3. likes ≥ 样本 P95；
    4. 高争议主题样本（按注释抽样）；5. 随机审计 5%（确定性种子）。
    """
    like_vals = sorted(likes_by_id.get(pid, 0) for pid in post_ids)
    p95 = like_vals[int(len(like_vals) * 0.95)] if like_vals else 0
    p50 = like_vals[len(like_vals) // 2] if like_vals else 0
    rng = random.Random(seed)
    audit_set = {pid for pid in post_ids if rng.random() < audit_ratio}
    queued: list[str] = []
    for pid in post_ids:
        a = annotations.get(pid)
        if a is None:
            queued.append(pid)
            continue
        if (a.confidence < ROUTE_REVIEW_MIN_CONFIDENCE
                or a.irony.value in ("明显", "无法判断")
                or (likes_by_id.get(pid, 0) >= p95 and likes_by_id.get(pid, 0) > p50)
                or (set(topics_by_id.get(pid, [])) & controversy_top_topics)
                or pid in audit_set):
            queued.append(pid)
    return queued


def node_route_review(state: dict) -> dict:
    anns = [Annotation.model_validate(a) for a in state["annotations"]]
    ann_by_id = {a.post_id: a for a in anns}
    posts = [CommunityPost.model_validate(p) for p in state["posts"]]
    likes = {p.post_id: p.likes for p in posts}
    topics_by_id = {a.post_id: a.topics for a in anns}
    queued = route_review(
        [a.post_id for a in anns], ann_by_id, likes,
        controversy_top_topics=set(),  # 首轮未知争议度，用规则 1-3+审计；聚合后再强化
        topics_by_id=topics_by_id,
    )
    return {"review_queue": queued}


# ---------- 6. 强模型复核 ----------

def node_annotate_strong(state: dict, llm_strong: BaseLLMClient) -> dict:
    study = StudyConfig.model_validate(state["study"])
    queue = set(state.get("review_queue") or [])
    posts = [CommunityPost.model_validate(p) for p in state["posts"]]
    posts_by_id = {p.post_id: p for p in posts}
    videos_by_id = {v["video_id"]: ContentItem.model_validate(v) for v in state.get("videos", [])}
    priors = state.get("topic_priors") or {}
    anns = [dict(a) for a in state["annotations"]]
    if queue:
        sel = [posts_by_id[pid] for pid in queue if pid in posts_by_id]
        strong = _annotate_posts(sel, priors, videos_by_id, llm_strong, AnnotateStage.STRONG, study)
        strong_by_id = {a["post_id"]: a for a in strong}
        anns = [strong_by_id.get(a["post_id"], a) for a in anns]
    return {"annotations": anns}


# ---------- 7. 等待人工（非阻塞标记） ----------

def node_await_human(state: dict) -> dict:
    # 高优先级结论 100% 人工复核由 review_queue 保证；此处仅记录待审数量
    return {"pending_human_reviews": len(state.get("review_queue") or [])}


# ---------- 8. 聚合（Python 计算） ----------

def node_aggregate(state: dict, human_modified_ids: set[str] | None = None) -> dict:
    study = StudyConfig.model_validate(state["study"])
    posts = [CommunityPost.model_validate(p) for p in state["posts"]]
    anns = [Annotation.model_validate(a) for a in state["annotations"]]
    videos = [ContentItem.model_validate(v) for v in state.get("videos", [])]
    metrics = aggregate_metrics(study, posts, anns, videos, human_modified_ids=human_modified_ids)
    metrics["embed_quality"] = state.get("embed_quality", "")
    return {"metrics": metrics}


# ---------- 9+10. 报告（程序化结论）+ 验证 ----------

def build_claims(metrics: dict) -> list[Claim]:
    claims: list[Claim] = []
    topics = metrics.get("topics", {})
    scope = "在所采样的 B 站讨论中"
    ranked_issues = sorted(
        metrics["composites"]["issue_priority"]["scores"].items(), key=lambda kv: -kv[1]
    )
    for t, score in ranked_issues[:3]:
        if t not in topics:
            continue
        ts = topics[t]
        nsr = ts["net_support_rate"]
        nsr_s = f"{nsr:+.2f}" if nsr is not None else "不可用"
        small = "（小样本）" if ts["count"] < 30 else ""
        ev = metrics.get("evidence_index", {}).get(t, {})
        ev_ids = [i for ids in ev.values() for i in ids][:3]
        claims.append(Claim(
            claim_id=f"issue-{t}",
            text=(f"{scope}，『{t}』为本版本重点运营问题方向，净支持率 {nsr_s}，"
                  f"争议度 {ts['controversy']:.2f}，样本 {ts['count']} 条{small}"),
            metric_ids=[f"topics.{t}.net_support_rate", f"topics.{t}.controversy",
                        f"composites.issue_priority.scores.{t}"],
            evidence_ids=ev_ids,
            topic_sample_size=ts["count"],
        ))
    ranked_opp = sorted(
        metrics["composites"]["opportunity"]["scores"].items(), key=lambda kv: -kv[1]
    )
    for t, score in ranked_opp[:2]:
        if t not in topics:
            continue
        ts = topics[t]
        sr = ts["support_rate"]
        sr_s = f"{sr:.0%}" if sr is not None else "不可用"
        small = "（小样本）" if ts["count"] < 30 else ""
        ev = metrics.get("evidence_index", {}).get(t, {})
        ev_ids = [i for ids in ev.values() for i in ids][:3]
        claims.append(Claim(
            claim_id=f"opp-{t}",
            text=(f"{scope}，『{t}』为本版本正向机会方向，支持率 {sr_s}，"
                  f"视频覆盖 {ts['video_count']} 个，样本 {ts['count']} 条{small}"),
            metric_ids=[f"topics.{t}.support_rate", f"composites.opportunity.scores.{t}"],
            evidence_ids=ev_ids,
            topic_sample_size=ts["count"],
        ))
    return claims


def node_report_and_verify(state: dict, render_fn: Callable[[dict, list[Claim]], str]) -> dict:
    metrics = state["metrics"]
    claims = build_claims(metrics)
    vr = verify_claims(claims)
    report_html = render_fn(metrics, claims) if vr.passed else None
    return {
        "claims": [c.__dict__ for c in claims],
        "verify_result": {"passed": vr.passed, "violations": vr.violations},
        "report_html": report_html,
    }
