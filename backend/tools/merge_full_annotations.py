# -*- coding: utf-8 -*-
"""合并全量标注批次：批次文件（JSON 数组，按 todo 顺序）→ 回填 post_id → Annotation JSONL。

批次标注对象用短 key：
  r=relevant, t=topics[], s=stance, e=emotion, i=intensity, y=irony,
  n=intent, q=issue_type, c=confidence, a=abstain_reason
用法: uv run python tools/merge_full_annotations.py <study> <batch_file> <batch_size>
"""
import json
import sys
from pathlib import Path

from liveops.schema import Annotation, AnnotateStage

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

KEYMAP = {
    "r": "relevant", "t": "topics", "s": "stance", "e": "emotion",
    "i": "intensity", "y": "irony", "n": "intent", "q": "issue_type",
    "c": "confidence", "a": "abstain_reason",
}


def main():
    study = sys.argv[1]
    batch_file = Path(sys.argv[2])
    batch_size = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    # 批次序号从文件名提取（b01 -> 1），用于定位 todo 偏移
    import re
    m = re.search(r"b(\d+)", batch_file.name)
    batch_no = int(m.group(1)) if m else 1

    todo = [json.loads(l) for l in open(DATA / "annotations" / f"{study}_todo.jsonl", encoding="utf-8")]
    batch = json.loads(batch_file.read_text(encoding="utf-8"))
    start = (batch_no - 1) * batch_size
    seg = todo[start:start + len(batch)]
    assert len(seg) == len(batch), f"批次长度不匹配: todo {len(seg)} vs 标注 {len(batch)}"

    out = DATA / "annotations" / f"{study}_full.jsonl"
    # 已合并的 post_id（幂等：重复合并同一批会覆盖）
    existing = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                a = Annotation.model_validate(json.loads(line))
                existing[a.post_id] = a

    n = 0
    for todo_item, raw in zip(seg, batch):
        pid = todo_item["post_id"]
        fields = {KEYMAP[k]: v for k, v in raw.items() if k in KEYMAP}
        fields.setdefault("topics", [])
        fields.setdefault("intensity", 0)
        fields.setdefault("confidence", 0.5)
        ann = Annotation(
            post_id=pid, run_id=study, model="dev-agent-strong",
            prompt_version="manual-full-v1", stage=AnnotateStage.STRONG,
            **fields,
        )
        existing[pid] = ann
        n += 1

    with open(out, "w", encoding="utf-8") as f:
        for pid in sorted(existing):
            f.write(existing[pid].model_dump_json() + "\n")
    print(f"[merge] {study}: 本批 {n} 条，累计 {len(existing)} 条 -> {out}")


if __name__ == "__main__":
    main()
