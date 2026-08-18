# -*- coding: utf-8 -*-
"""登录态采集数据的落盘工具：读 nodeRepl 持久化输出文件，追加到 raw_rows.jsonl。

用法: uv run python tools/import_login_rows.py <artifacts_path>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "login-test" / "raw_rows.jsonl"


def main():
    art = Path(sys.argv[1])
    # artifacts 文件：第一行是完整 JSON 对象，末尾有 "Structured content:" 尾巴
    first_line = art.read_text(encoding="utf-8").splitlines()[0]
    d = json.loads(first_line)
    rows = d["rows"]
    with open(OUT, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    total = sum(1 for _ in open(OUT, encoding="utf-8"))
    print(f"落盘 {len(rows)} 条（next 至 {d.get('next')}，stopped={d.get('stopped')}），累计 {total} 条")


if __name__ == "__main__":
    main()
