"""审核服务：队列、HumanReview 记录、人工覆盖合并、证据回溯。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import config
from .evidence import EvidenceItem
from .schema import Annotation, AnnotateStage, CommunityPost, HumanReview


class RunStore:
    """runs/ 目录访问层。"""

    def __init__(self, runs_dir: str | Path | None = None):
        self.dir = Path(runs_dir) if runs_dir else config.RUNS_DIR

    def list_runs(self) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.dir.glob("*/manifest.json"), reverse=True):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
                out.append({
                    "run_id": m["run_id"], "study_id": m["study_id"],
                    "status": m["status"], "created_at": m["created_at"],
                    "models": m.get("models", {}), "cost_cny": m.get("cost_cny", 0),
                })
            except Exception:
                continue
        return out

    def run_dir(self, run_id: str) -> Path:
        return self.dir / run_id

    def load_state(self, run_id: str) -> dict | None:
        p = self.run_dir(run_id) / "state.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def load_manifest(self, run_id: str) -> dict | None:
        p = self.run_dir(run_id) / "manifest.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def annotations(self, run_id: str) -> list[Annotation]:
        st = self.load_state(run_id)
        if not st:
            return []
        return [Annotation.model_validate(a) for a in st.get("annotations", [])]

    def posts(self, run_id: str) -> list[CommunityPost]:
        st = self.load_state(run_id)
        if not st:
            return []
        return [CommunityPost.model_validate(p) for p in st.get("posts", [])]

    def metrics(self, run_id: str) -> dict | None:
        st = self.load_state(run_id)
        return (st or {}).get("metrics")

    def human_reviews_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "human_overrides.jsonl"


REVIEW_FIELDS = ["relevant", "topics", "stance", "emotion", "intensity",
                 "irony", "intent", "issue_type"]


class ReviewService:
    def __init__(self, store: RunStore | None = None):
        self.store = store or RunStore()

    def queue(self, run_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """审核队列：review_queue 中的样本 + 原文 + 当前标签 + 人工修正状态。"""
        st = self.store.load_state(run_id)
        if not st:
            return []
        anns = {a["post_id"]: a for a in st.get("annotations", [])}
        posts = {p["post_id"]: p for p in st.get("posts", [])}
        videos = {v["video_id"]: v for v in st.get("videos", [])}
        reviewed = self._reviewed_map(run_id)
        queue = st.get("review_queue") or []
        out = []
        for pid in queue:
            a, p = anns.get(pid), posts.get(pid)
            if not a or not p:
                continue
            v = videos.get(p["video_id"], {})
            out.append({
                "post_id": pid,
                "text": p["text"][:300],
                "published_at": p["published_at"],
                "likes": p.get("likes", 0),
                "parent_id": p.get("parent_id"),
                "video_title": v.get("title", ""),
                "video_url": v.get("url", ""),
                "current": a,
                "human_modified": pid in reviewed,
                "review_count": len(reviewed.get(pid, [])),
            })
        return out[offset : offset + limit]

    def _reviewed_map(self, run_id: str) -> dict[str, list[HumanReview]]:
        path = self.store.human_reviews_path(run_id)
        out: dict[str, list[HumanReview]] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = HumanReview.model_validate(json.loads(line))
                    out.setdefault(r.post_id, []).append(r)
        return out

    def submit(self, run_id: str, post_id: str, field_changes: list[dict],
               reviewer: str, reason: str = "") -> HumanReview | None:
        """提交人工修正：field_changes=[{field, after}]，与当前标签 diff 后落盘。
        与模型建议不同且未给原因 → 拒绝（API 层契约）。"""
        anns = {a.post_id: a for a in self.store.annotations(run_id)}
        a = anns.get(post_id)
        if a is None:
            raise KeyError(f"post {post_id} 不在 run {run_id} 中")
        changed = False
        last = HumanReview(
            review_id=f"rv-{uuid4().hex[:12]}", post_id=post_id, run_id=run_id,
            field="", before="", after="", reason=reason or "接受模型标签",
            reviewer=reviewer, reviewed_at=datetime.now(timezone.utc),
        )
        for ch in field_changes:
            f = ch.get("field")
            if f not in REVIEW_FIELDS:
                raise ValueError(f"非法字段: {f}")
            before = getattr(a, f)
            after = ch.get("after")
            if before == after:
                continue  # 无变化不记录
            if not reason:
                raise ValueError("与模型建议不同时必须填写修改原因")
            changed = True
            last = HumanReview(
                review_id=f"rv-{uuid4().hex[:12]}", post_id=post_id, run_id=run_id,
                field=f, before=json.dumps(before, ensure_ascii=False) if not isinstance(before, str) else before,
                after=json.dumps(after, ensure_ascii=False) if not isinstance(after, str) else after,
                reason=reason, reviewer=reviewer,
                reviewed_at=datetime.now(timezone.utc),
            )
            with open(self.store.human_reviews_path(run_id), "a", encoding="utf-8") as fh:
                fh.write(last.model_dump_json() + "\n")
        if not changed:
            # 记录"接受"（审计：确认过但未修改）
            with open(self.store.human_reviews_path(run_id), "a", encoding="utf-8") as fh:
                fh.write(last.model_dump_json() + "\n")
        return last

    def merged_annotations(self, run_id: str) -> tuple[list[Annotation], set[str]]:
        """人工覆盖合并后的标注（重新聚合用）。返回 (annotations, modified_ids)。"""
        anns = self.store.annotations(run_id)
        by_pid = {a.post_id: a for a in anns}
        reviewed = self._reviewed_map(run_id)
        modified: set[str] = set()
        for pid, reviews in reviewed.items():
            a = by_pid.get(pid)
            if not a:
                continue
            updates: dict[str, Any] = {}
            for r in sorted(reviews, key=lambda r: r.reviewed_at):
                if r.field in REVIEW_FIELDS:
                    try:
                        val = json.loads(r.after)
                    except (json.JSONDecodeError, TypeError):
                        val = r.after
                    updates[r.field] = val
            if updates:
                data = a.model_dump(mode="json")
                data.update(updates)
                data["stage"] = AnnotateStage.HUMAN.value
                data["needs_review"] = False
                by_pid[pid] = Annotation.model_validate(data)
                modified.add(pid)
        return list(by_pid.values()), modified

    def evidence(self, run_id: str, evidence_id: str) -> EvidenceItem | None:
        m = self.store.metrics(run_id)
        if not m:
            return None
        item = (m.get("evidence_items") or {}).get(evidence_id)
        return EvidenceItem(**item) if item else None
