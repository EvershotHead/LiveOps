"""LLM 输出契约：与 prompts/v1 配套的严格 JSON Schema 模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..schema.enums import Emotion, Intent, Irony, IssueType, Stance, is_valid_topic


class AnnotateOut(BaseModel):
    """annotate-v1 的模型输出契约（extra=forbid）。"""

    model_config = ConfigDict(extra="forbid")

    relevant: bool | None = None
    topics: list[str] = Field(default_factory=list, max_length=6)
    stance: Stance | None = None
    emotion: Emotion | None = None
    intensity: int = Field(default=0, ge=0, le=3)
    irony: Irony = Irony.NONE
    intent: Intent | None = None
    issue_type: IssueType | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_span: str = Field(default="", max_length=120)
    abstain_reason: str | None = None

    @field_validator("topics")
    @classmethod
    def _topics_ok(cls, v: list[str]) -> list[str]:
        for t in v:
            if not is_valid_topic(t):
                raise ValueError(f"非法主题: {t}")
        if len(set(v)) != len(v):
            raise ValueError("主题重复")
        return v

    @field_validator("abstain_reason")
    @classmethod
    def _abstain(cls, v, info):
        if info.data.get("relevant") is None and not v:
            raise ValueError("relevant=null 必须给 abstain_reason")
        return v


def to_annotation_fields(out: AnnotateOut) -> dict:
    """AnnotateOut → Annotation 字段（调用方补 post_id/model/prompt_version/stage）。"""
    return out.model_dump()
