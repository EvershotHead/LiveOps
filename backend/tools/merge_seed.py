# -*- coding: utf-8 -*-
"""把人工（开发 Agent）撰写的种子标注批次合并为 GoldLabel JSONL。

输入批次格式: tools/seed_batches/<study>_b<N>.json = {"post_id": {label fields}}
输出: data/gold/<study>_seed.jsonl（GoldLabel，annotator=dev-agent, strong_model_seed）
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from liveops.schema import GoldLabel

ROOT = Path(__file__).resolve().parents[2]


def merge(study_id: str, batch_files: list[str]):
    out = ROOT / "data" / "gold" / f"{study_id}_seed.jsonl"
    existing = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                g = GoldLabel.model_validate(json.loads(line))
                existing[g.post_id] = g
    n_new = 0
    for bf in batch_files:
        data = json.loads(Path(bf).read_text(encoding="utf-8"))
        for pid, fields in data.items():
            if fields is None:
                continue
            base = {
                "post_id": pid, "study_id": study_id,
                "annotator": "dev-agent", "annotator_type": "strong_model_seed",
                "annotated_at": datetime.now(timezone.utc).isoformat(),
                "note": fields.pop("note", ""),
            }
            base.update(fields)
            existing[pid] = GoldLabel.model_validate(base)
            n_new += 1
    with open(out, "w", encoding="utf-8") as f:
        for pid in sorted(existing):
            f.write(existing[pid].model_dump_json() + "\n")
    print(f"[merge] {study_id}: 共 {len(existing)} 条（本批新增 {n_new}）-> {out}")


if __name__ == "__main__":
    merge(sys.argv[1], sys.argv[2:])
