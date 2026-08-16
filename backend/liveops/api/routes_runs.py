"""任务与导入路由（本地模式）。"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import config
from ..fixtures import load_fixture
from ..harness.graph import HarnessDeps, run_pipeline
from ..harness.lock import RunLock, RunLockError
from ..ingest import (
    FileReadError,
    IngestError,
    apply_mapping,
    project_rows,
    read_file,
    suggest_mapping,
    validate_posts,
)
from ..llm import MockLLM, ResponseCache, ScriptedLLM, get_client, register_scripted
from ..llm.prompts import v1
from ..anonymize import make_anon_fn
from ..schema import CommunityPost, ContentItem, StudyConfig, GameName
from ..service_review import RunStore

router = APIRouter(prefix="/api")
_store = RunStore()


class ImportPreview(BaseModel):
    file_token: str
    columns: list[str]
    suggested_mapping: dict[str, str | None]
    preview_rows: list[dict]


# 内存暂存（单机单任务场景足够；文件本身也留在临时目录）
_pending_tables: dict[str, object] = {}


@router.post("/import/preview")
def import_preview(file: UploadFile = File(...)) -> ImportPreview:
    try:
        raw = file.file.read()
    except Exception as e:
        raise HTTPException(400, f"读取失败: {e}")
    suffix = Path(file.filename or "x.csv").suffix
    tmp = config.DATA_DIR / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    token = f"imp-{len(_pending_tables)}-{Path(file.filename).stem}"[:60]
    p = tmp / f"upload{suffix}"
    p.write_bytes(raw)
    try:
        table = read_file(p)
    except IngestError as e:
        raise HTTPException(422, str(e))
    _pending_tables[token] = table
    return ImportPreview(
        file_token=token, columns=table.columns,
        suggested_mapping=suggest_mapping(table), preview_rows=table.preview(20),
    )


class ValidateReq(BaseModel):
    file_token: str
    mapping: dict[str, str | None]
    study: dict  # StudyConfig 字段


class ValidateResp(BaseModel):
    ok: bool
    summary: str
    errors: list[dict]
    post_count: int
    missing_required: list[str]


@router.post("/import/validate", response_model=ValidateResp)
def import_validate(req: ValidateReq):
    table = _pending_tables.get(req.file_token)
    if table is None:
        raise HTTPException(404, "导入会话失效，请重新上传")
    mp = apply_mapping(table, req.mapping)
    if mp.missing_required:
        raise HTTPException(422, f"缺少最少必需字段: {mp.missing_required}")
    study = StudyConfig.model_validate(req.study)
    rows = project_rows(table, req.mapping)
    anon_fn = make_anon_fn(study.study_id)
    rep = validate_posts(rows, anon_salt_fn=anon_fn)
    # 暂存通过校验的 posts 供创建任务
    posts = [p.model_dump(mode="json") for p in rep.posts]
    _pending_tables[req.file_token + ":posts"] = posts
    return ValidateResp(
        ok=rep.ok, summary=rep.summary(), errors=rep.errors[:50],
        post_count=rep.valid_count, missing_required=[],
    )


class CreateRunReq(BaseModel):
    file_token: str | None = None
    study: dict
    videos: list[dict] = []


@router.post("/runs")
def create_run(req: CreateRunReq):
    if req.file_token:
        posts = _pending_tables.get(req.file_token + ":posts")
        if not posts:
            raise HTTPException(404, "未校验的导入数据，请先 /import/validate")
    else:
        fx = load_fixture(req.study.get("study_id") or "synthetic-100") \
            if req.study.get("study_id", "").startswith("synthetic") else None
        if fx is None:
            # 真实研究数据：data/raw/<study_id> 冻结样本
            raw = config.DATA_DIR / "raw" / req.study["study_id"]
            posts = [json.loads(l) for l in (raw / "posts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
            req.videos = [json.loads(l) for l in (raw / "videos.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        else:
            posts = [p.model_dump(mode="json") for p in fx.posts]
            req.videos = [v.model_dump(mode="json") for v in fx.videos]

    study = StudyConfig.model_validate(req.study)
    post_objs = [CommunityPost.model_validate(p) for p in posts]
    video_objs = [ContentItem.model_validate(v) for v in req.videos]

    cache = ResponseCache(config.RUNS_DIR / "llm-cache.sqlite")
    if req.study.get("scripted_replay"):
        # 纵向切片模式：回放种子标注（不消耗密钥）
        fx = load_fixture("synthetic_100")
        register_scripted(v1.ANNOTATE_VERSION, fx.seed_annotations)
        llm = ScriptedLLM(cache=cache)
    else:
        llm = get_client(cache)
        if isinstance(llm, MockLLM):
            raise HTTPException(409, "未配置 LLM 密钥（LLM_BASE_URL/LLM_API_KEY/LLM_MODEL），"
                                     "请填写 .env 后重启，或使用 scripted_replay 模式")

    def _worker():
        try:
            with RunLock(config.RUNS_DIR / ".lock"):
                run_pipeline(study, post_objs, video_objs, HarnessDeps(llm),
                             runs_dir=config.RUNS_DIR)
        except RunLockError as e:
            print(f"[run] {e}")
        except Exception as e:
            print(f"[run] failed: {e}")

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started", "study_id": study.study_id}


@router.get("/runs")
def list_runs():
    return _store.list_runs()


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    m = _store.load_manifest(run_id)
    if not m:
        raise HTTPException(404, "run 不存在")
    stages = {k: v["status"] for k, v in (m.get("stage_states") or {}).items()}
    return {"run_id": run_id, "manifest": m, "stage_status": stages}
