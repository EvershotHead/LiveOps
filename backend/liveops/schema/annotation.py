"""Annotation（模型/人工标注）与 HumanReview（人工修正审计）。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    AnnotateStage,
    AnnotatorType,
    Emotion,
    Intent,
    Irony,
    IssueType,
    Stance,
    is_valid_topic,
)


class Annotation(BaseModel):
    """单条评论的结构化标注。

    relevant=None 表示弃权（abstain_reason 必填）。
    网络梗/反串/引用/语境不足允许"无法判断"，禁止强行二分。
    """

    model_config = ConfigDict(extra="forbid")

    post_id: str
    run_id: str = ""

    relevant: bool | None = None
    topics: list[str] = Field(default_factory=list)
    new_topic_ids: list[str] = Field(default_factory=list)

    stance: Stance | None = None
    emotion: Emotion | None = None
    intensity: int = Field(default=0, ge=0, le=3)
    irony: Irony = Irony.NONE
    intent: Intent | None = None
    issue_type: IssueType | None = None

    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_span: str = ""            # 简短证据片段（原文截取），不保存模型思维过程
    abstain_reason: str | None = None

    model: str = ""                    # 产出该标注的模型/标注器标识
    prompt_version: str = ""
    stage: AnnotateStage = AnnotateStage.CHEAP
    needs_review: bool = False

    @field_validator("topics")
    @classmethod
    def _topics_valid(cls, v: list[str]) -> list[str]:
        for t in v:
            if not is_valid_topic(t):
                raise ValueError(f"非法主题标签: {t}")
        return v

    @field_validator("abstain_reason")
    @classmethod
    def _abstain_consistency(cls, v, info):
        # 弃权时必须给原因
        if info.data.get("relevant") is None and not v:
            raise ValueError("relevant=None（弃权）时必须填写 abstain_reason")
        return v


class GoldLabel(BaseModel):
    """金标准条目：两层策略（strong_model_seed / human）。"""

    model_config = ConfigDict(extra="forbid")

    post_id: str
    study_id: str
    annotator: str                    # 标注员标识
    annotator_type: AnnotatorType
    annotated_at: datetime

    relevant: bool | None = None
    topics: list[str] = Field(default_factory=list)
    stance: Stance | None = None
    emotion: Emotion | None = None
    intensity: int = Field(default=0, ge=0, le=3)
    irony: Irony = Irony.NONE
    intent: Intent | None = None
    issue_type: IssueType | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    evidence_span: str = ""
    abstain_reason: str | None = None
    note: str = ""

    @field_validator("topics")
    @classmethod
    def _topics_valid(cls, v: list[str]) -> list[str]:
        for t in v:
            if not is_valid_topic(t):
                raise ValueError(f"非法主题标签: {t}")
        return v


class HumanReview(BaseModel):
    """人工审核的字段级修改记录，可审计回放。"""

    model_config = ConfigDict(extra="forbid")

    review_id: str
    post_id: str
    run_id: str = ""
    field: str                        # 被修改的标注字段名
    before: str                       # 修改前值（序列化）
    after: str                        # 修改后值（序列化）
    reason: str                       # 修改原因（与建议不同时必填，API 层强制）
    reviewer: str
    reviewed_at: datetime
