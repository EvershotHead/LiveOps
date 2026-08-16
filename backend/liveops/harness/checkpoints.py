"""阶段级断点：state.json 记录每个阶段状态与输出哈希，支持 kill 后续跑。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..schema import AnalysisRun, RunStatus, StageState, StageStatus


def output_hash(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class CheckpointStore:
    def __init__(self, run_dir: str | Path):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.run_dir / "state.json"
        self.manifest_path = self.run_dir / "manifest.json"

    # ---------- manifest ----------
    def load_manifest(self) -> AnalysisRun | None:
        if not self.manifest_path.exists():
            return None
        return AnalysisRun.model_validate(json.loads(self.manifest_path.read_text(encoding="utf-8")))

    def save_manifest(self, run: AnalysisRun) -> None:
        self.manifest_path.write_text(
            run.model_dump_json(indent=2), encoding="utf-8"
        )

    # ---------- state ----------
    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def save_state(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    # ---------- 阶段状态 ----------
    def stage_status(self, stage: str) -> StageState | None:
        run = self.load_manifest()
        if run is None:
            return None
        return run.stage_states.get(stage)

    def should_skip(self, stage: str, dataset_hash: str) -> bool:
        """阶段已完成、产物 hash 一致、且数据集未变 → 可跳过。"""
        run = self.load_manifest()
        if run is None or run.dataset_hash != dataset_hash:
            return False
        ss = run.stage_states.get(stage)
        return bool(ss and ss.status == StageStatus.DONE and ss.output_hash)

    def mark_stage(self, run: AnalysisRun, stage: str, status: StageStatus,
                   output_hash: str = "", error: str | None = None,
                   items: int = 0) -> AnalysisRun:
        run.stage_states[stage] = StageState(
            stage=stage, status=status, output_hash=output_hash,
            started_at=run.stage_states[stage].started_at if stage in run.stage_states else datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc) if status in (StageStatus.DONE, StageStatus.FAILED, StageStatus.SKIPPED) else None,
            error=error, items_processed=items,
        )
        self.save_manifest(run)
        return run

    def persist_stage_output(self, stage: str, payload: Any) -> str:
        p = self.run_dir / f"{stage}.json"
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return output_hash(payload)
