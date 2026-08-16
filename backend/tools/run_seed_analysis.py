# -*- coding: utf-8 -*-
"""种子样本全量分析：两游戏 400 条样本端到端 + 向量基线评测 + 回放一致性校验。

口径（如实）：
- 标注层 = strong_model_seed（开发 Agent 种子），经 ScriptedLLM 回放进入管道；
  回放与金标 100% 一致是【管道正确性校验】，不作为模型质量证据。
- 向量基线（无密钥模式）：嵌入质心相关性/主题分类 vs 金标，给出真实 Macro-F1。
- LLM 标注质量：未测量（待用户配置密钥后一键重跑）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from liveops.cluster import assign_topics, compute_topic_centroids
from liveops.embed import embed_texts
from liveops.evaluate import (
    ALL_TOPIC_LABELS, EMOTIONS, IRONY, STANCES,
    cohen_kappa, confusion_matrix, expected_calibration_error,
    grouped_split, macro_f1, multilabel_macro_f1,
)
from liveops.evaluate.gold import load_gold
from liveops.fixtures import load_fixture
from liveops.harness.graph import HarnessDeps, run_pipeline
from liveops.llm import ScriptedLLM, register_scripted
from liveops.llm.prompts import v1
from liveops.schema import CommunityPost, ContentItem, StudyConfig

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RUNS = ROOT / "runs"
UTC = timezone.utc

STUDY_IDS = ["genshin-6.8", "wuthering-3.5"]
TARGETS = {"relevance": 0.90, "topics": 0.70, "stance": 0.75, "emotion": 0.65, "irony": 0.60}


def load_seed_dataset(study_id: str):
    frozen = DATA / "raw" / study_id / "frozen"
    study = StudyConfig.model_validate(json.loads((frozen / "study.json").read_text(encoding="utf-8")))
    posts_all = [CommunityPost.model_validate(json.loads(l))
                 for l in (frozen / "posts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    videos = [ContentItem.model_validate(json.loads(l))
              for l in (frozen / "videos.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    gold = {g.post_id: g for g in load_gold(DATA / "gold" / f"{study_id}_seed.jsonl")}
    posts = [p for p in posts_all if p.post_id in gold]
    return study, posts, videos, gold


def replay_annotations(gold: dict) -> dict[str, dict]:
    """GoldLabel → annotate-v1 输出格式（ScriptedLLM 回放）。"""
    out = {}
    for pid, g in gold.items():
        out[pid] = {
            "relevant": g.relevant,
            "topics": g.topics,
            "stance": g.stance.value if g.stance else None,
            "emotion": g.emotion.value if g.emotion else None,
            "intensity": g.intensity,
            "irony": g.irony.value,
            "intent": g.intent.value if g.intent else None,
            "issue_type": g.issue_type.value if g.issue_type else None,
            "confidence": g.confidence,
            "evidence_span": g.evidence_span or "（种子标注）",
            "abstain_reason": g.abstain_reason if g.relevant is None else None,
        }
    return out


def vector_baseline(posts, gold: dict) -> dict:
    """嵌入质心基线 vs 金标：相关性 + 主题（真实数字）。"""
    texts = [p.text for p in posts]
    res = embed_texts(texts)

    def embed_fn(ts):
        return embed_texts(ts).vectors

    centroids = compute_topic_centroids(embed_fn)
    # 相关性基线：与主题质心最大余弦 ≥ 阈值 → relevant
    from liveops.cluster import cosine
    sims_max = []
    for v in res.vectors:
        sims_max.append(max(cosine(v, c) for c in centroids.values()))
    thr = 0.30  # 哈希嵌入下经验阈值（bge-m3 时分布不同，重新自适应）
    # 自适应：取金标相关样本的 P10 分位作为阈值（弱基线，非调参作弊：只用训练组）
    split = grouped_split([p.video_id for p in posts], test_size=0.3, seed=42)
    train_idx, test_idx = split["train"], split["test"]
    train_sims = [sims_max[i] for i in train_idx if gold[posts[i].post_id].relevant is True]
    if train_sims:
        thr = sorted(train_sims)[max(0, int(len(train_sims) * 0.10))]

    y_true = [("相关" if gold[posts[i].post_id].relevant is True else
               "无关" if gold[posts[i].post_id].relevant is False else "弃权") for i in test_idx]
    y_pred = [("相关" if sims_max[i] >= thr else "无关") for i in test_idx]
    rel_eval = macro_f1(y_true, y_pred, ["相关", "无关"])

    # 主题基线（多标签，测试组；阈值由训练组金标主题自适应）
    train_topic_sims = []
    for i in train_idx:
        g = gold[posts[i].post_id]
        if not g.topics:
            continue
        v = res.vectors[i]
        best = max((cosine(v, centroids[t]) for t in g.topics if t in centroids), default=0)
        train_topic_sims.append(best)
    topic_thr = sorted(train_topic_sims)[max(0, int(len(train_topic_sims) * 0.25))] if train_topic_sims else 0.30
    assign = assign_topics([posts[i].post_id for i in test_idx],
                           [posts[i].text for i in test_idx],
                           [res.vectors[i] for i in test_idx],
                           centroids, threshold=topic_thr, min_cluster_size=5)
    t_true = [set(gold[posts[i].post_id].topics) for i in test_idx]
    t_pred = [set(assign.assignments[posts[i].post_id].topics) for i in test_idx]
    topic_eval = multilabel_macro_f1(t_true, t_pred, ALL_TOPIC_LABELS)

    return {
        "relevance": {"macro_f1": rel_eval["macro_f1"], "abstain_rate": 0.0,
                      "threshold": thr, "embed_quality": res.embed_quality},
        "topics": {"macro_f1": topic_eval["macro_f1"], "threshold": topic_thr},
        "split": {"train": len(train_idx), "test": len(test_idx),
                  "train_videos": len(split["train_videos"]), "test_videos": len(split["test_videos"])},
    }


def evaluate_run(annotations, gold, posts) -> dict:
    """回放一致性（管道正确性）+ 校准 + 分组切分报告。"""
    by_pid = {a["post_id"]: a for a in annotations}
    common = [p.post_id for p in posts if p.post_id in by_pid and p.post_id in gold]
    y_stance_t, y_stance_p, y_emotion_t, y_emotion_p, y_irony_t, y_irony_p = [], [], [], [], [], []
    confs, corrects = [], []
    agree = 0
    for pid in common:
        g, a = gold[pid], by_pid[pid]
        gs = g.stance.value if g.stance else None
        if gs:
            y_stance_t.append(gs); y_stance_p.append(a["stance"])
        ge = g.emotion.value if g.emotion else None
        if ge:
            y_emotion_t.append(ge); y_emotion_p.append(a["emotion"])
        y_irony_t.append(g.irony.value); y_irony_p.append(a["irony"])
        confs.append(a["confidence"])
        corrects.append((g.relevant is None and a["relevant"] is None) or g.relevant == a["relevant"])
        agree += int((g.relevant is None and a["relevant"] is None) or g.relevant == a["relevant"])
    return {
        "replay_agreement": agree / len(common) if common else None,
        "stance_f1": macro_f1(y_stance_t, y_stance_p, STANCES),
        "emotion_f1": macro_f1(y_emotion_t, y_emotion_p, EMOTIONS),
        "irony_f1": macro_f1(y_irony_t, y_irony_p, IRONY),
        "ece": expected_calibration_error(confs, corrects),
        "confusion": {
            "立场": confusion_matrix(y_stance_t, [p if p else "弃权" for p in y_stance_p], STANCES),
        },
    }


def main():
    results = {}
    for study_id in STUDY_IDS:
        study, posts, videos, gold = load_seed_dataset(study_id)
        print(f"[run] {study_id}: posts={len(posts)} gold={len(gold)}")
        replay = replay_annotations(gold)
        register_scripted(v1.ANNOTATE_VERSION, replay)
        result = run_pipeline(study, posts, videos,
                              HarnessDeps(ScriptedLLM()), runs_dir=RUNS,
                              run_id=f"seed-{study_id}")
        state = result.state
        # 评测
        baseline = vector_baseline(posts, gold)
        replay_eval = evaluate_run(state["annotations"], gold, posts)
        m = state["metrics"]
        evaluation = {
            "gold_layer": "strong_model_seed",
            "n_gold": len(gold),
            "n_evaluated": baseline["split"]["test"],
            "relevance": {"macro_f1": baseline["relevance"]["macro_f1"]},
            "topics": {"macro_f1": baseline["topics"]["macro_f1"]},
            "stance": None, "emotion": None, "irony": None,
            "ece": replay_eval["ece"],
            "kappa": None,
            "cost_cny": 0.0,
            "throughput_per_min": round(len(posts) / max(result.run.duration_s, 0.001) * 60, 1),
            "confusion": {"立场": replay_eval["confusion"]["立场"], "主题": None},
            "targets": TARGETS,
            "notes": [
                f"向量基线（{baseline['relevance']['embed_quality']}）：按视频分组切分，"
                f"训练 {baseline['split']['train']} / 测试 {baseline['split']['test']} 条",
                f"回放一致性 {replay_eval['replay_agreement']:.1%}（ScriptedLLM 回放种子标注，"
                "用于验证管道与聚合正确性，不代表模型质量）",
                "LLM 标注质量：未测量——配置 LLM 密钥后运行 uv run liveops run --study ... 可获得真实评测",
                "立场/情绪/反讽基线：无监督向量基线不适用，未测量",
            ],
            "baseline_detail": baseline,
            "replay_detail": {"stance_f1": replay_eval["stance_f1"]["macro_f1"],
                              "irony_f1": replay_eval["irony_f1"]["macro_f1"]},
        }
        # 写入 run 目录
        run_dir = RUNS / f"seed-{study_id}"
        (run_dir / "evaluation.json").write_text(
            json.dumps(evaluation, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        # 保存用于演示导出的 metrics
        (run_dir / "metrics.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        results[study_id] = {
            "run_id": f"seed-{study_id}",
            "relevant_posts": m["dataset"]["relevant_posts"],
            "baseline_relevance_f1": baseline["relevance"]["macro_f1"],
            "baseline_topic_f1": baseline["topics"]["macro_f1"],
            "claims": len(state.get("claims", [])),
            "verify_passed": state["verify_result"]["passed"],
            "report": str(run_dir / "report.html"),
        }
        print(f"[done] {study_id}: 有效 {m['dataset']['relevant_posts']} | 基线相关性F1 "
              f"{baseline['relevance']['macro_f1']:.3f} | 主题F1 {baseline['topics']['macro_f1']:.3f} | "
              f"结论验证 {'通过' if state['verify_result']['passed'] else '未通过'}")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
