"""AnalysisRun：每次分析任务的完整溯源与阶段状态。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_HUMAN = "awaiting_human"   # 等待人工审核
    PAUSED = "paused"                   # 异常暂停（可续跑）
    COMPLETED = "completed"
    FAILED = "failed"
    COLLECTION_BLOCKED = "collection_blocked"  # 采集被风控硬停


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"     # 断点续跑时 hash 一致跳过
    FAILED = "failed"


class StageState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    status: StageStatus = StageStatus.PENDING
    output_hash: str = ""   # 阶段产物 hash，断点续跑一致性判断
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    items_processed: int = 0
    cost_cny: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0


class ErrorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    at: datetime
    kind: str              # 如 llm_invalid_output / rate_limited / hard_stop
    message: str
    sample: str = ""       # 最多保留 200 字符的上下文样本


class AnalysisRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    study_id: str
    created_at: datetime
    dataset_hash: str                     # 数据集内容 hash（冻结样本）
    config_snapshot: dict[str, Any]       # StudyConfig 序列化
    models: dict[str, str] = Field(default_factory=dict)        # {"cheap": "...", "strong": "..."}
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    label_set_version: str = "v1.0"
    code_version: str = ""                # git SHA
    params: dict[str, Any] = Field(default_factory=dict)
    status: RunStatus = RunStatus.PENDING
    stage_states: dict[str, StageState] = Field(default_factory=dict)
    cost_cny: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    duration_s: float = 0.0
    errors: list[ErrorRecord] = Field(default_factory=list)
