"""标注工作台路由。"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..service_review import ReviewService, RunStore

router = APIRouter(prefix="/api")
_store = RunStore()
_svc = ReviewService(_store)


class FieldChange(BaseModel):
    field: str
    after: object


class SubmitReq(BaseModel):
    post_id: str
    changes: list[FieldChange]
    reviewer: str = "local-user"
    reason: str = ""


@router.get("/review/{run_id}/queue")
def review_queue(run_id: str, limit: int = 50, offset: int = 0):
    q = _svc.queue(run_id, limit=limit, offset=offset)
    return {"run_id": run_id, "count": len(q), "items": q}


@router.post("/review/{run_id}/submit")
def review_submit(run_id: str, req: SubmitReq):
    try:
        r = _svc.submit(
            run_id, req.post_id,
            [c.model_dump() for c in req.changes],
            reviewer=req.reviewer, reason=req.reason,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))
    return {"ok": True, "review_id": r.review_id if r else None}


@router.get("/review/{run_id}/history")
def review_history(run_id: str):
    path = _store.human_reviews_path(run_id)
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return {"run_id": run_id, "reviews": out}


class RecomputeReq(BaseModel):
    apply_human_overrides: bool = True


@router.post("/review/{run_id}/recompute")
def recompute(run_id: str, req: RecomputeReq):
    """人工覆盖合并后重新聚合指标（Python 重算）。"""
    from ..metrics.aggregate import aggregate_metrics
    from ..schema import Annotation, CommunityPost, ContentItem, StudyConfig
    st = _store.load_state(run_id)
    if not st:
        raise HTTPException(404, "run 不存在")
    anns, modified = (_svc.merged_annotations(run_id)
                      if req.apply_human_overrides
                      else (_store.annotations(run_id), set()))
    posts = [CommunityPost.model_validate(p) for p in st["posts"]]
    videos = [ContentItem.model_validate(v) for v in st.get("videos", [])]
    study = StudyConfig.model_validate(st["study"])
    metrics = aggregate_metrics(study, posts, anns, videos, human_modified_ids=modified)
    state_path = _store.run_dir(run_id) / "state.json"
    st["metrics"] = metrics
    state_path.write_text(json.dumps(st, ensure_ascii=False, indent=2, default=str),
                          encoding="utf-8")
    (_store.run_dir(run_id) / "aggregate.json").write_text(
        json.dumps(metrics, ensure_ascii=False, default=str), encoding="utf-8")
    return {"ok": True, "human_modified": len(modified)}
