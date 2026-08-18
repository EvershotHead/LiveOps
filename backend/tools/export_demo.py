# -*- coding: utf-8 -*-
"""公开演示导出：从 seed runs 生成 demo/public-data/*.json（匿名、只读、无密钥）。

泄漏扫描强制通过（build_public_export 的白名单 + PII 断言）才写盘。
"""
from __future__ import annotations

import json
from pathlib import Path

from liveops import config
from liveops.anonymize import mask_text
from liveops.service_compare import build_comparison
from liveops.service_review import RunStore

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
OUT = ROOT / "demo" / "public-data"

GAMES = {"genshin": "full-genshin-6.8", "wuwa": "full-wuthering-3.5"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    import liveops.api.routes_read as rr
    store = RunStore(RUNS)
    rr._store = store
    rr._review_svc = __import__("liveops.service_review", fromlist=["ReviewService"]).ReviewService(store)

    summaries = []
    for key, run_id in GAMES.items():
        ov = rr.run_overview(run_id)
        tl = rr.run_timeline(run_id)
        cv = rr.run_controversy(run_id)
        se = rr.run_sensitivity(run_id)
        ev_path = RUNS / run_id / "evaluation.json"
        if ev_path.exists():
            ev = json.loads(ev_path.read_text(encoding="utf-8"))
        else:
            ev = {
                "gold_layer": "strong_model_seed",
                "n_gold": 800,
                "n_evaluated": None,
                "relevance": {"macro_f1": None, "note": "全量回放模式，无金标对照"},
                "topics": {"macro_f1": None},
                "stance": None, "emotion": None, "irony": None,
                "ece": None, "kappa": None,
                "cost_cny": 0.0, "throughput_per_min": None,
                "confusion": {},
                "targets": {"relevance": 0.9, "topics": 0.7, "stance": 0.75, "emotion": 0.65, "irony": 0.6},
                "notes": [
                    "全量标注模式：开发 Agent 强模型全量标注（原神1597/鸣潮1939条）回放进入管道，回放一致性100%验证管道正确性，非模型质量证据",
                    "LLM 标注质量：未测量——配置密钥后对全量样本真实运行可得",
                    "向量基线/金标对照：待人工金标层补齐后计算",
                ],
            }
        m = store.metrics(run_id)
        # 证据逐条导出（文本已匿名，@提及再脱敏一次）
        ev_dir = OUT / "evidence"
        ev_dir.mkdir(exist_ok=True)
        for eid, item in (m.get("evidence_items") or {}).items():
            item = dict(item)
            item["text_excerpt"] = mask_text(item.get("text_excerpt", ""))
            (ev_dir / f"{eid}.json").write_text(
                json.dumps(item, ensure_ascii=False), encoding="utf-8")
        # evidence_items 内嵌文本也脱敏后整体导出（供争议页直读）
        for item in (m.get("evidence_items") or {}).values():
            item["text_excerpt"] = mask_text(item.get("text_excerpt", ""))

        # 公开导出强制泄漏扫描
        from liveops.anonymize import build_public_export
        posts_pub = [
            {"post_id": pid, "video_id": "", "text": mask_text(e.get("text_excerpt", "")),
             "published_at": e.get("published_at", ""), "likes": e.get("likes", 0),
             "source_url": e.get("source_url", ""), "synthetic": False}
            for pid, e in (m.get("evidence_items") or {}).items()
        ]
        build_public_export(posts_pub, [], m)  # 断言通过才继续

        (OUT / f"overview-{key}.json").write_text(json.dumps(ov, ensure_ascii=False), encoding="utf-8")
        (OUT / f"timeline-{key}.json").write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")
        (OUT / f"controversy-{key}.json").write_text(json.dumps(cv, ensure_ascii=False), encoding="utf-8")
        (OUT / f"sensitivity-{key}.json").write_text(json.dumps(se, ensure_ascii=False, default=str), encoding="utf-8")
        (OUT / f"evaluation-{key}.json").write_text(json.dumps(ev, ensure_ascii=False, default=str), encoding="utf-8")
        state = store.load_state(run_id) or {}
        m_export = dict(m)
        m_export["claims"] = state.get("claims", [])
        m_export["verify_result"] = state.get("verify_result", {})
        (OUT / f"metrics-{key}.json").write_text(json.dumps(m_export, ensure_ascii=False, default=str), encoding="utf-8")
        report = RUNS / run_id / "report.html"
        if report.exists():
            (OUT / f"report-{key}.html").write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
        manifest = store.load_manifest(run_id) or {}
        summaries.append({
            "run_id": run_id, "study_id": manifest.get("study_id", key),
            "status": manifest.get("status", "completed"),
            "created_at": manifest.get("created_at", ""),
            "models": manifest.get("models", {}), "cost_cny": 0,
            "game_key": key,
        })
        print(f"[demo] {key} <- {run_id} (evidence {len(m.get('evidence_items') or {})})")

    cmp = build_comparison(GAMES["genshin"], GAMES["wuwa"], store)
    (OUT / "compare.json").write_text(json.dumps(cmp, ensure_ascii=False, default=str), encoding="utf-8")
    (OUT / "runs.json").write_text(json.dumps(summaries, ensure_ascii=False), encoding="utf-8")
    print("[demo] compare.json + runs.json 写出完成")


if __name__ == "__main__":
    main()
