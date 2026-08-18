# -*- coding: utf-8 -*-
"""导出全量标注待办清单：规范化后的帖子（排除已标种子），供开发 Agent 逐批标注。

输出: data/annotations/<study>_todo.jsonl（每行: post_id, text, is_sub, day）
"""
import json
from datetime import date
from pathlib import Path

from liveops.normalize import day_offset, normalize_posts
from liveops.schema import CommunityPost, StudyConfig

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

STUDIES = {
    "genshin-6.8": ("genshin", "6.8", date(2026, 7, 1)),
    "wuthering-3.5": ("wuthering_waves", "3.5", date(2026, 7, 10)),
}


def export(study_id: str):
    game, ver, t0 = STUDIES[study_id]
    study = StudyConfig(study_id=study_id, game=game, version_label=ver, t0_date=t0)
    posts = [CommunityPost.model_validate(json.loads(l))
             for l in open(DATA / "raw" / study_id / "frozen" / "posts.jsonl", encoding="utf-8") if l.strip()]
    kept, rep = normalize_posts(posts, study)
    gold = {json.loads(l)["post_id"] for l in open(DATA / "gold" / f"{study_id}_seed.jsonl", encoding="utf-8") if l.strip()}
    todo = [p for p in kept if p.post_id not in gold]
    todo.sort(key=lambda p: (0 if p.parent_id else 1, p.published_at))
    out = DATA / "annotations" / f"{study_id}_todo.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for p in todo:
            f.write(json.dumps({
                "post_id": p.post_id, "text": p.text.replace("\n", " "),
                "is_sub": bool(p.parent_id), "day": day_offset(t0, p.published_at.date()),
            }, ensure_ascii=False) + "\n")
    print(f"{study_id}: 导出待标 {len(todo)} 条 -> {out}")


if __name__ == "__main__":
    for sid in STUDIES:
        export(sid)
