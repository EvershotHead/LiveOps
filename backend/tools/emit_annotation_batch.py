# -*- coding: utf-8 -*-
"""标注轮次辅助：按批次输出紧凑清单，供开发 Agent 逐批标注。

用法:
  .venv/Scripts/python.exe tools/emit_annotation_batch.py <study> seed <n>     # 种子第 n 批(100条/批)
  .venv/Scripts/python.exe tools/emit_annotation_batch.py <study> todo <n>    # 全量 todo 第 n 批
输出每行: seq|post_id|text(截断)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def main():
    study, kind, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    size = 100
    if kind == "seed":
        rows = [json.loads(l) for l in open(DATA / "gold" / f"{study}_sample.jsonl", encoding="utf-8") if l.strip()]
    else:
        rows = [json.loads(l) for l in open(DATA / "annotations" / f"{study}_todo.jsonl", encoding="utf-8") if l.strip()]
    seg = rows[(n - 1) * size: n * size]
    if not seg:
        print(f"[empty] batch {n} 超出范围（共 {len(rows)} 条）")
        return
    for i, r in enumerate(seg, 1):
        text = r["text"][:100].replace("|", "／")
        print(f"{i}|{r['post_id']}|{text}")
    print(f"[{study} {kind} batch {n}: {len(seg)} 条 / 总 {len(rows)}]")


if __name__ == "__main__":
    main()
