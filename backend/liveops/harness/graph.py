"""受约束状态图执行器：LangGraph 定义图结构 + 自研阶段执行循环（磁盘断点）。

- build_langgraph()：用 LangGraph StateGraph 声明同一组节点（结构校验 + mermaid 导出）。
- run_pipeline()：顺序执行节点，每阶段写 state.json / manifest，可 kill 后续跑。
- 单任务文件锁；dataset_hash 变化则拒绝复用断点。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .. import config
from ..llm import BaseLLMClient, RateLimitedError
from ..report.render import render_report_html
from ..report.verify import Claim
from ..schema import AnalysisRun, CommunityPost, ContentItem, StudyConfig, RunStatus, StageStatus, ErrorRecord
from ..evidence import EvidenceItem
from .checkpoints import CheckpointStore, output_hash
from .lock import RunLock
from . import nodes as N


def _git_sha() -> str:
    try:
        import subprocess
        root = config.REPO_ROOT
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=root,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return "unknown"


def dataset_hash_of(posts: list[dict], videos: list[dict], study: dict) -> str:
    return output_hash({"posts": posts, "videos": videos, "study": study})


class HarnessDeps:
    """节点依赖注入（LLM 客户端等），便于测试。"""

    def __init__(self, llm_cheap: BaseLLMClient, llm_strong: BaseLLMClient | None = None):
        self.llm_cheap = llm_cheap
        self.llm_strong = llm_strong or llm_cheap


class PipelineResult:
    def __init__(self, state: dict, run: AnalysisRun):
        self.state = state
        self.run = run


def run_pipeline(
    study: StudyConfig,
    posts: list[CommunityPost],
    videos: list[ContentItem],
    deps: HarnessDeps,
    runs_dir: str | Path | None = None,
    *,
    run_id: str | None = None,
    human_modified_ids: set[str] | None = None,
    fail_at_stage: str | None = None,   # 测试用：模拟中途崩溃
) -> PipelineResult:
    runs_dir = Path(runs_dir) if runs_dir else config.RUNS_DIR
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + study.study_id
    run_dir = runs_dir / run_id

    posts_s = [p.model_dump(mode="json") for p in posts]
    videos_s = [v.model_dump(mode="json") for v in videos]
    study_s = study.model_dump(mode="json")
    d_hash = dataset_hash_of(posts_s, videos_s, study_s)

    store = CheckpointStore(run_dir)
    existing = store.load_manifest()
    if existing is not None and existing.dataset_hash != d_hash:
        raise ValueError("数据集哈希与既有断点不一致，拒绝续跑；请使用新 run_id")

    run = existing or AnalysisRun(
        run_id=run_id, study_id=study.study_id,
        created_at=datetime.now(timezone.utc),
        dataset_hash=d_hash, config_snapshot=study_s,
        models={"cheap": deps.llm_cheap.name, "strong": deps.llm_strong.name},
        prompt_versions={"annotate": "annotate-v1"},
        label_set_version=study.label_set_version,
        code_version=_git_sha(),
        params={"embed_model": config.EMBED_MODEL},
        status=RunStatus.RUNNING,
    )
    run.status = RunStatus.RUNNING
    store.save_manifest(run)

    state: dict[str, Any] = store.load_state()
    state.setdefault("study", study_s)
    state.setdefault("posts", posts_s)
    state.setdefault("videos", videos_s)
    started = datetime.now(timezone.utc)

    node_fns: dict[str, Callable[[dict], dict]] = {
        "normalize": N.node_normalize,
        "relevance_filter": N.node_relevance_filter,
        "embed_cluster": N.node_embed_cluster,
        "annotate_cheap": lambda s: N.node_annotate_cheap(s, deps.llm_cheap),
        "route_review": N.node_route_review,
        "annotate_strong": lambda s: N.node_annotate_strong(s, deps.llm_strong),
        "await_human": N.node_await_human,
        "aggregate": lambda s: N.node_aggregate(s, human_modified_ids),
        "report": lambda s: N.node_report_and_verify(s, _render_with_evidence(s)),
    }
    # verify 阶段在 report 节点内部完成（结论验证不通过则不产出报告）
    node_fns["verify"] = lambda s: {"verify_final": s.get("verify_result", {})}

    try:
        cur_stage = ""
        for stage in N.STAGES:
            cur_stage = stage
            if store.should_skip(stage, d_hash):
                # 续跑：把已完成阶段的产物回载进 state（manifest 保持 DONE 不变）
                p = run_dir / f"{stage}.json"
                if p.exists():
                    state.update(json.loads(p.read_text(encoding="utf-8")))
                continue
            run = store.mark_stage(run, stage, StageStatus.RUNNING)
            if fail_at_stage == stage:  # 测试注入：模拟进程被杀
                raise RuntimeError(f"injected failure at {stage}")
            update = node_fns[stage](state)
            state.update(update)
            oh = store.persist_stage_output(stage, update)
            run = store.mark_stage(run, stage, StageStatus.DONE, output_hash=oh,
                                   items=len(update.get("annotations", update.get("posts", []))) if isinstance(update, dict) else 0)
            store.save_state(state)
        run.status = RunStatus.COMPLETED
    except RateLimitedError as e:
        run.status = RunStatus.PAUSED
        if cur_stage:
            run = store.mark_stage(run, cur_stage, StageStatus.FAILED, error=str(e)[:200])
        run.errors.append(ErrorRecord(
            stage=cur_stage or "llm", at=datetime.now(timezone.utc),
            kind="rate_limited", message=str(e)[:300]))
        store.save_manifest(run)
        store.save_state(state)
        raise
    except Exception as e:
        run.status = RunStatus.FAILED
        if cur_stage:
            run = store.mark_stage(run, cur_stage, StageStatus.FAILED, error=str(e)[:200])
        run.errors.append(ErrorRecord(
            stage=cur_stage or "pipeline", at=datetime.now(timezone.utc),
            kind=type(e).__name__, message=str(e)[:300]))
        store.save_manifest(run)
        store.save_state(state)
        raise

    run.duration_s = (datetime.now(timezone.utc) - started).total_seconds()
    run.tokens_in = deps.llm_cheap.usage.tokens_in + deps.llm_strong.usage.tokens_in
    run.tokens_out = deps.llm_cheap.usage.tokens_out + deps.llm_strong.usage.tokens_out
    store.save_manifest(run)

    # 产物：报告 HTML（验证通过才有）
    if state.get("report_html"):
        (run_dir / "report.html").write_text(state["report_html"], encoding="utf-8")
    return PipelineResult(state=state, run=run)


def _render_with_evidence(state: dict) -> Callable[[dict, list[Claim]], str]:
    def render(metrics: dict, claims: list[Claim]) -> str:
        from ..evidence import EvidenceItem
        ev_raw = metrics.get("evidence_items") or {}
        ev = {k: EvidenceItem(**v) for k, v in ev_raw.items()}
        return render_report_html(metrics, claims, ev)
    return render


def build_langgraph(deps: HarnessDeps | None = None):
    """LangGraph 状态图声明（结构校验与 mermaid 架构图导出用）。"""
    from typing import TypedDict
    from langgraph.graph import StateGraph

    if deps is None:
        from ..llm import get_client
        deps = HarnessDeps(get_client())

    class GState(TypedDict, total=False):
        study: dict
        posts: list
        videos: list
        candidate_post_ids: list
        topic_priors: dict
        annotations: list
        review_queue: list
        metrics: dict
        claims: list
        report_html: str

    g = StateGraph(GState)
    g.add_node("normalize", N.node_normalize)
    g.add_node("relevance_filter", N.node_relevance_filter)
    g.add_node("embed_cluster", N.node_embed_cluster)
    g.add_node("annotate_cheap", lambda s: N.node_annotate_cheap(s, deps.llm_cheap))
    g.add_node("route_review", N.node_route_review)
    g.add_node("annotate_strong", lambda s: N.node_annotate_strong(s, deps.llm_strong))
    g.add_node("await_human", N.node_await_human)
    g.add_node("aggregate", lambda s: N.node_aggregate(s))
    g.add_node("report", lambda s: N.node_report_and_verify(s, _render_with_evidence(s)))
    g.add_node("verify", lambda s: {"verify_final": s.get("verify_result", {})})
    g.set_entry_point("normalize")
    g.add_edge("normalize", "relevance_filter")
    g.add_edge("relevance_filter", "embed_cluster")
    g.add_edge("embed_cluster", "annotate_cheap")
    g.add_edge("annotate_cheap", "route_review")
    g.add_edge("route_review", "annotate_strong")
    g.add_edge("annotate_strong", "await_human")
    g.add_edge("await_human", "aggregate")
    g.add_edge("aggregate", "report")
    g.add_edge("report", "verify")
    g.add_edge("verify", "__end__")
    return g
