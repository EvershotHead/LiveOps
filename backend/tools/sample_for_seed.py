# -*- coding: utf-8 -*-
"""种子标注抽样：从冻结样本中分层抽取 400 条（按视频×阶段×楼层 分层，确定性）。

抽样约束：
- 仅时间窗内（T-7~T+28）评论
- 单视频 ≤ 10 条、单作者 ≤ 3 条（种子样本内平衡）
- 覆盖根评论与楼中楼
输出: data/gold/<study>_sample.jsonl（待标注）与进度文件。
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from liveops.normalize import day_offset
from liveops.schema import CommunityPost, StudyConfig

DATA = Path(__file__).resolve().parents[2] / "data"


def load_frozen(study_id: str):
    raw = DATA / "raw" / study_id / "frozen"
    study = StudyConfig.model_validate(json.loads((raw / "study.json").read_text(encoding="utf-8")))
    posts = [CommunityPost.model_validate(json.loads(l))
             for l in (raw / "posts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return study, posts


def stratified_sample(posts: list[CommunityPost], study: StudyConfig, n=400, seed=42) -> list[CommunityPost]:
    in_win = [p for p in posts if study.window.in_window(day_offset(study.t0_date, p.published_at.date()))]
    rng = random.Random(seed)
    rng.shuffle(in_win)
    per_video: dict[str, int] = defaultdict(int)
    per_user: dict[str, int] = defaultdict(int)
    picked: list[CommunityPost] = []
    # 第一轮：均匀视频覆盖
    for p in in_win:
        if len(picked) >= n:
            break
        if per_video[p.video_id] >= 10 or per_user[p.anon_user_id] >= 3:
            continue
        picked.append(p)
        per_video[p.video_id] += 1
        per_user[p.anon_user_id] += 1
    # 第二轮：若不足（视频太多导致），放宽视频上限到 12
    if len(picked) < n:
        for p in in_win:
            if len(picked) >= n:
                break
            if p in picked or per_video[p.video_id] >= 12 or per_user[p.anon_user_id] >= 3:
                continue
            picked.append(p)
            per_video[p.video_id] += 1
            per_user[p.anon_user_id] += 1
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", required=True)
    ap.add_argument("--n", type=int, default=400)
    args = ap.parse_args()
    study, posts = load_frozen(args.study)
    picked = stratified_sample(posts, study, args.n)
    out = DATA / "gold" / f"{args.study}_sample.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for p in picked:
            f.write(json.dumps({
                "post_id": p.post_id, "video_id": p.video_id,
                "parent_id": p.parent_id, "text": p.text,
                "published_at": p.published_at.isoformat(),
                "likes": p.likes, "day_offset": day_offset(study.t0_date, p.published_at.date()),
            }, ensure_ascii=False) + "\n")
    sub = sum(1 for p in picked if p.parent_id)
    print(f"[sample] {args.study}: {len(picked)} 条（楼中楼 {sub}，视频 {len({p.video_id for p in picked})} 个）-> {out}")


if __name__ == "__main__":
    main()
