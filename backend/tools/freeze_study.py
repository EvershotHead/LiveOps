# -*- coding: utf-8 -*-
"""冻结研究样本：配额校验 → frozen/ 目录 + 数据集哈希 + 冻结报告。

受限采样如实记录：配额不满足项不会掩盖，写入 limitation 说明。
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from liveops.collector.sampling import validate_sample
from liveops.harness.checkpoints import output_hash
from liveops.schema import CommunityPost, ContentItem, StudyConfig

UTC = timezone.utc
DATA = Path(__file__).resolve().parents[2] / "data"

STUDY_DEFS = {
    "genshin-6.8": dict(game="genshin", version_label="6.8", t0=date(2026, 7, 1),
                        search_terms=["原神6.8 PV", "原神6.8 攻略", "原神6.8 体验",
                                      "原神6.8 二创", "原神6.8 卡池"]),
    "wuthering-3.5": dict(game="wuthering_waves", version_label="3.5", t0=date(2026, 7, 10),
                          search_terms=["鸣潮3.5 PV", "鸣潮3.5 攻略", "鸣潮3.5 体验",
                                        "鸣潮3.5 二创", "鸣潮3.5 卡池"]),
}


def freeze(study_id: str) -> Path:
    raw = DATA / "raw" / study_id
    cfg = STUDY_DEFS[study_id]
    study = StudyConfig(study_id=study_id, t0_date=cfg["t0"], search_terms=cfg["search_terms"],
                        game=cfg["game"], version_label=cfg["version_label"],  # type: ignore[arg-type]
                        locked_at=datetime.now(UTC),
                        lock_evidence=["docs/sampling-protocol.md 版本锁定证据"])
    posts = [CommunityPost.model_validate(json.loads(l))
             for l in (raw / "posts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    videos = [ContentItem.model_validate(json.loads(l))
              for l in (raw / "videos.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    rep = validate_sample(posts, videos, study)
    frozen = raw / "frozen"
    frozen.mkdir(parents=True, exist_ok=True)
    posts_s = [p.model_dump(mode="json") for p in posts]
    videos_s = [v.model_dump(mode="json") for v in videos]
    study_s = study.model_dump(mode="json")
    d_hash = output_hash({"posts": posts_s, "videos": videos_s, "study": study_s})

    (frozen / "posts.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in posts_s), encoding="utf-8")
    (frozen / "videos.jsonl").write_text(
        "\n".join(json.dumps(v, ensure_ascii=False) for v in videos_s), encoding="utf-8")
    (frozen / "study.json").write_text(json.dumps(study_s, ensure_ascii=False, indent=2), encoding="utf-8")

    # 数据集画像
    by_cat: dict[str, int] = {}
    for v in videos:
        by_cat[v.category.value] = by_cat.get(v.category.value, 0) + 1
    per_video: dict[str, int] = {}
    for p in posts:
        per_video[p.video_id] = per_video.get(p.video_id, 0) + 1
    max_share = max(per_video.values()) / len(posts) if posts else 0

    report = {
        "study_id": study_id, "frozen_at": datetime.now(UTC).isoformat(),
        "dataset_hash": d_hash, "quota_ok": rep.ok,
        "quota_checks": rep.checks,
        "profile": {
            "posts": len(posts), "videos": len(videos),
            "videos_by_category": by_cat,
            "max_single_video_share": round(max_share, 4),
            "sub_replies": sum(1 for p in posts if p.parent_id),
            "collect_requests": json.loads((raw / "collect_state.json").read_text(encoding="utf-8"))["requests"],
        },
        "limitations": [],
    }
    if not rep.ok:
        failed = [c for c in rep.checks if not c["passed"]]
        report["limitations"].append(
            "受限公开采样：未登录会话下 B 站仅返回每视频首页评论与楼中楼，"
            "有效评论量与配额目标存在缺口（详见 quota_checks 失败项）。"
            "本数据集为『受限公开采样』口径，UI/报告必须展示该限制；"
            "补足配额路径：用户自行导出评论后经文件导入。"
        )
    (frozen / "freeze_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[freeze] {study_id}: posts={len(posts)} videos={len(videos)} quota_ok={rep.ok} hash={d_hash[:12]}")
    for c in rep.checks:
        print("  ", "✅" if c["passed"] else "❌", c["name"], c["detail"])
    return frozen


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", required=True)
    args = ap.parse_args()
    freeze(args.study)
