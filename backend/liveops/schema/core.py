"""Canonical Schema 核心对象：StudyConfig / ContentItem / CommunityPost。

导入数据最少要求 text、published_at、source_url（见 validator）。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import AuthorType, GameName, PostFlag, VideoCategory

UTC = timezone.utc


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PhaseWindow(StrictModel):
    """相对 T0 的天数区间（闭区间）。默认 T-7 ~ T+28，分三段。"""

    preheat: tuple[int, int] = (-7, -1)
    launch: tuple[int, int] = (0, 7)
    ferment: tuple[int, int] = (8, 28)

    def in_window(self, day_offset: int) -> bool:
        return self.preheat[0] <= day_offset <= self.ferment[1]

    def phase_of(self, day_offset: int) -> Literal["preheat", "launch", "ferment"] | None:
        for name in ("preheat", "launch", "ferment"):
            lo, hi = getattr(self, name)
            if lo <= day_offset <= hi:
                return name  # type: ignore[return-value]
        return None


class StudyConfig(StrictModel):
    study_id: str
    game: GameName
    version_label: str
    t0_date: date
    window: PhaseWindow = PhaseWindow()
    search_terms: list[str] = Field(default_factory=list)
    video_quota: tuple[int, int] = (40, 60)
    comment_quota: tuple[int, int] = (4000, 5000)
    max_share_per_video: float = 0.10
    min_videos_per_category: int = 6
    analysis_template: str = "v1"
    label_set_version: str = "v1.0"
    locked_at: datetime | None = None
    lock_evidence: list[str] = Field(default_factory=list)  # 版本锁定检索证据 URL


class StatsSnapshot(StrictModel):
    view: int = 0
    like: int = 0
    coin: int = 0
    favorite: int = 0
    share: int = 0
    comment: int = 0
    snapshot_at: datetime | None = None


class ContentItem(StrictModel):
    video_id: str                       # B 站 BV 号或导入系统生成的替代 ID
    title: str
    url: str
    published_at: datetime
    category: VideoCategory
    author_type: AuthorType = AuthorType.UGC
    stats_snapshot: StatsSnapshot = StatsSnapshot()
    sampled_at: datetime | None = None
    search_term_used: str = ""
    search_rank: int = 0
    sampling_reason: str = ""

    @field_validator("video_id")
    @classmethod
    def _video_id_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("video_id 不能为空")
        return v


class CommunityPost(StrictModel):
    post_id: str
    video_id: str
    parent_id: str | None = None        # 楼中楼父评论
    text: str
    published_at: datetime
    likes: int = 0
    reply_count: int = 0
    anon_user_id: str                   # HMAC-SHA256(study_salt, uid)[:16]
    collected_at: datetime | None = None
    dedup_group: str | None = None
    flags: list[PostFlag] = []
    source_url: str = ""                # 评论所在页（导入最少字段）

    @field_validator("text")
    @classmethod
    def _text_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("评论正文不能为空")
        return v
