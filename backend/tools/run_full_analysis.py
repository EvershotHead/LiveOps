# -*- coding: utf-8 -*-
"""全量标注分析：种子(GoldLabel) + 全量(Annotation) → 回放 → 完整 pipeline。

口径：标注层 = strong_model_seed（开发 Agent 种子 400 条）+ 开发 Agent 全量标注
（data/annotations/<study>_full.jsonl），经 ScriptedLLM 回放进入管道。
"""
import json
from pathlib import Path

from liveops.harness.graph import HarnessDeps, run_pipeline
from liveops.llm import ScriptedLLM, register_scripted
from liveops.llm.prompts import v1
from liveops.schema import Annotation, CommunityPost, ContentItem, StudyConfig

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RUNS = ROOT / "runs"

STUDIES = {
    "genshin-6.8": ("genshin", "6.8", "2026-07-01"),
    "wuthering-3.5": ("wuthering_waves", "3.5", "2026-07-10"),
}


def load_study(study_id: str):
    game, ver, t0 = STUDIES[study_id]
    frozen = DATA / "raw" / study_id / "frozen"
    study = StudyConfig.model_validate(json.loads((frozen / "study.json").read_text(encoding="utf-8")))
    posts = [CommunityPost.model_validate(json.loads(l))
             for l in (frozen / "posts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    videos = [ContentItem.model_validate(json.loads(l))
              for l in (frozen / "videos.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return study, posts, videos


def load_all_annotations(study_id: str) -> dict[str, dict]:
    """种子 GoldLabel + 全量 Annotation → annotate-v1 回放格式。"""
    out = {}
    # 种子
    for line in (DATA / "gold" / f"{study_id}_seed.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        g = json.loads(line)
        out[g["post_id"]] = {
            "relevant": g["relevant"], "topics": g.get("topics", []),
            "stance": g.get("stance"), "emotion": g.get("emotion"),
            "intensity": g.get("intensity", 0), "irony": g.get("irony", "无"),
            "intent": g.get("intent"), "issue_type": g.get("issue_type"),
            "confidence": g.get("confidence", 0.5),
            "evidence_span": g.get("evidence_span", ""),
            "abstain_reason": g.get("abstain_reason") if g.get("relevant") is None else None,
        }
    # 全量
    for line in (DATA / "annotations" / f"{study_id}_full.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        a = Annotation.model_validate(json.loads(line))
        out[a.post_id] = {
            "relevant": a.relevant, "topics": a.topics,
            "stance": a.stance.value if a.stance else None,
            "emotion": a.emotion.value if a.emotion else None,
            "intensity": a.intensity, "irony": a.irony.value,
            "intent": a.intent.value if a.intent else None,
            "issue_type": a.issue_type.value if a.issue_type else None,
            "confidence": a.confidence, "evidence_span": a.evidence_span,
            "abstain_reason": a.abstain_reason if a.relevant is None else None,
        }
    return out


def main():
    results = {}
    for study_id in STUDIES:
        study, posts, videos = load_study(study_id)
        annotations = load_all_annotations(study_id)
        print(f"[run] {study_id}: posts={len(posts)} 标注={len(annotations)}")
        register_scripted(v1.ANNOTATE_VERSION, annotations)
        result = run_pipeline(study, posts, videos, HarnessDeps(ScriptedLLM()),
                              runs_dir=RUNS, run_id=f"full-{study_id}")
        state = result.state
        m = state["metrics"]
        run_dir = RUNS / f"full-{study_id}"
        (run_dir / "metrics.json").write_text(json.dumps(m, ensure_ascii=False, default=str), encoding="utf-8")
        results[study_id] = {
            "run_id": f"full-{study_id}",
            "relevant_posts": m["dataset"]["relevant_posts"],
            "abstain": m["dataset"]["abstain_count"],
            "irrelevant": m["dataset"]["irrelevant_count"],
            "claims": len(state.get("claims", [])),
            "verify_passed": state["verify_result"]["passed"],
        }
        print(f"[done] {study_id}: 有效 {m['dataset']['relevant_posts']} | 弃权 {m['dataset']['abstain_count']} "
              f"| 无关 {m['dataset']['irrelevant_count']} | 结论验证 {'通过' if state['verify_result']['passed'] else '未通过'}")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
