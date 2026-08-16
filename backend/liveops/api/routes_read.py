"""只读数据路由：总览/主题/时间线/争议/对照/证据/报告。"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from .. import config
from ..service_compare import build_comparison
from ..service_review import ReviewService, RunStore

router = APIRouter(prefix="/api")
_store = RunStore()
_review_svc = ReviewService(_store)


def _run_or_404(run_id: str) -> dict:
    m = _store.load_state(run_id)
    if not m:
        raise HTTPException(404, f"run {run_id} 不存在")
    return m


@router.get("/runs/{run_id}/metrics")
def run_metrics(run_id: str):
    m = _store.metrics(run_id)
    if not m:
        raise HTTPException(404, "metrics 未生成（任务可能未完成）")
    return m


@router.get("/runs/{run_id}/overview")
def run_overview(run_id: str):
    """总览页数据：数据覆盖 + 主题分布 + 正负信号 + 风险/机会。"""
    m = _store.metrics(run_id)
    if not m:
        raise HTTPException(404, "metrics 未生成")
    issues = sorted(m["composites"]["issue_priority"]["scores"].items(), key=lambda kv: -kv[1])
    opps = sorted(m["composites"]["opportunity"]["scores"].items(), key=lambda kv: -kv[1])
    return {
        "scope_statement": m["scope_statement"],
        "study": {"study_id": m["study_id"], "game": m["game"], "version": m["version_label"],
                  "t0": m["t0_date"]},
        "dataset": m["dataset"],
        "overall": m["overall"],
        "topic_shares": [
            {"topic": t, "share": ts["topic_share"], "count": ts["count"],
             "net_support": ts["net_support_rate"], "controversy": ts["controversy"]}
            for t, ts in sorted(m["topics"].items(), key=lambda kv: -kv[1]["count"])
        ],
        "top_risks": [{"topic": t, "score": s} for t, s in issues[:5]],
        "top_opportunities": [{"topic": t, "score": s} for t, s in opps[:5]],
        "weights": {
            "issue_priority": m["composites"]["issue_priority"]["weights"],
            "opportunity": m["composites"]["opportunity"]["weights"],
        },
        "disclaimer": m["composites"]["issue_priority"]["disclaimer"],
    }


@router.get("/runs/{run_id}/timeline")
def run_timeline(run_id: str):
    """版本时间线：主题/净支持率随相对日变化。"""
    m = _store.metrics(run_id)
    if not m:
        raise HTTPException(404, "metrics 未生成")
    series = {}
    for t, ts in m["topics"].items():
        series[t] = {"daily_counts": ts["daily_counts"], "trend_speed": ts["trend_speed"]}
    return {"t0": m["t0_date"], "window": [-7, 28], "topics": series,
            "scope_statement": m["scope_statement"]}


@router.get("/runs/{run_id}/controversy")
def run_controversy(run_id: str):
    """社区争议：冲突话题、观点矩阵、代表性证据。"""
    m = _store.metrics(run_id)
    if not m:
        raise HTTPException(404, "metrics 未生成")
    topics = sorted(m["topics"].items(), key=lambda kv: -kv[1]["controversy"])[:8]
    rows = []
    for t, ts in topics:
        ev = m["evidence_index"].get(t, {})
        rows.append({
            "topic": t, "controversy": ts["controversy"],
            "reply_conflict": ts["reply_conflict"],
            "stance": ts["stance"], "net_support": ts["net_support_rate"],
            "evidence": {k: v[:3] for k, v in ev.items()},
        })
    return {"rows": rows, "scope_statement": m["scope_statement"]}


@router.get("/runs/{run_id}/sensitivity")
def run_sensitivity(run_id: str):
    m = _store.metrics(run_id)
    if not m:
        raise HTTPException(404, "metrics 未生成")
    return m["composites"]["sensitivity"]


@router.get("/runs/{run_id}/evaluation")
def run_evaluation(run_id: str):
    p = _store.run_dir(run_id) / "evaluation.json"
    if not p.exists():
        raise HTTPException(404, "评测未生成（需运行 tools/run_seed_analysis.py 或真实 LLM 任务）")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/compare/{run_a}/{run_b}")
def compare_runs(run_a: str, run_b: str):
    try:
        return build_comparison(run_a, run_b, _store)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.get("/evidence/{run_id}/{evidence_id}")
def evidence(run_id: str, evidence_id: str):
    e = _review_svc.evidence(run_id, evidence_id) if config.MODE == "local" else None
    if e is None and config.MODE == "demo":
        data = _demo_metrics()
        item = (data or {}).get("evidence_items", {}).get(evidence_id)
        if item:
            from ..evidence import EvidenceItem
            e = EvidenceItem(**item)
    if e is None:
        raise HTTPException(404, "证据不存在")
    from dataclasses import asdict
    return asdict(e)


@router.get("/runs/{run_id}/report", response_class=HTMLResponse)
def run_report(run_id: str):
    p = _store.run_dir(run_id) / "report.html"
    if not p.exists():
        raise HTTPException(404, "报告未生成（需结论验证通过）")
    return HTMLResponse(p.read_text(encoding="utf-8"))


# ---------- 演示模式 ----------
def _demo_metrics() -> dict | None:
    p = config.DEMO_DATA_DIR / "metrics.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/demo/overview")
def demo_overview():
    if config.MODE != "demo":
        raise HTTPException(400, "仅演示模式可用")
    return _demo_metrics()
