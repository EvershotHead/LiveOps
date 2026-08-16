"""证据链：EvidenceID 体系与回溯。

EvidenceID = post_id（评论在数据集内天然唯一）。
每条指标/结论引用 EvidenceID 列表，UI 可下钻到匿名化原文 + 来源视频链接。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable

from .schema import Annotation, CommunityPost, ContentItem


@dataclass
class EvidenceItem:
    evidence_id: str            # = post_id
    video_id: str
    video_title: str
    video_url: str
    text_excerpt: str           # ≤80 字
    published_at: str
    likes: int
    topics: list[str]
    stance: str | None
    emotion: str | None
    irony: str
    model_label_stage: str      # cheap | strong | human
    confidence: float
    human_modified: bool
    source_url: str


def build_evidence_items(
    posts: Iterable[CommunityPost],
    annotations: dict[str, Annotation],
    videos: dict[str, ContentItem],
    *,
    excerpt_len: int = 80,
    human_modified_ids: set[str] | None = None,
) -> dict[str, EvidenceItem]:
    human_modified_ids = human_modified_ids or set()
    out: dict[str, EvidenceItem] = {}
    for p in posts:
        a = annotations.get(p.post_id)
        if a is None:
            continue
        v = videos.get(p.video_id)
        out[p.post_id] = EvidenceItem(
            evidence_id=p.post_id,
            video_id=p.video_id,
            video_title=v.title if v else p.video_id,
            video_url=v.url if v else p.source_url,
            text_excerpt=p.text[:excerpt_len],
            published_at=p.published_at.isoformat(),
            likes=p.likes,
            topics=a.topics,
            stance=a.stance.value if a.stance else None,
            emotion=a.emotion.value if a.emotion else None,
            irony=a.irony.value,
            model_label_stage=a.stage.value,
            confidence=a.confidence,
            human_modified=p.post_id in human_modified_ids,
            source_url=p.source_url,
        )
    return out


def representative_evidence(
    evidence: dict[str, EvidenceItem],
    topic: str,
    *,
    per_stance: int = 3,
) -> dict[str, list[str]]:
    """某主题的代表性证据：按立场分组，组内按互动量取前 N。返回 stance -> [evidence_id]。"""
    by_stance: dict[str, list[EvidenceItem]] = {}
    for e in evidence.values():
        if topic in e.topics:
            by_stance.setdefault(e.stance or "未标注", []).append(e)
    result: dict[str, list[str]] = {}
    for stance, items in by_stance.items():
        items.sort(key=lambda x: (-x.likes, x.evidence_id))
        result[stance] = [i.evidence_id for i in items[:per_stance]]
    return result


def to_jsonable(evidence: dict[str, EvidenceItem]) -> dict[str, dict]:
    return {k: asdict(v) for k, v in evidence.items()}
