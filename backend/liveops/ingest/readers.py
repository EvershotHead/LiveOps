"""数据读取：CSV / XLSX / JSON / JSONL → RawTable（统一行列表 + 列名）。

设计要点：
- 损坏文件抛 FileReadError（含人类可读信息），不 crash。
- 空数据（无行/无列）抛 EmptyDataError。
- 编码自动探测（utf-8-sig / gbk 兜底）。
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class IngestError(Exception):
    """导入错误基类。"""


class FileReadError(IngestError):
    pass


class EmptyDataError(IngestError):
    pass


class UnsupportedFormatError(IngestError):
    pass


@dataclass
class RawTable:
    """统一中间表：列名 + 行字典列表。"""

    columns: list[str]
    rows: list[dict[str, Any]]
    source_path: str = ""
    row_count: int = 0
    format: str = ""
    truncated_reason: str | None = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.row_count = len(self.rows)

    def preview(self, n: int = 20) -> list[dict[str, Any]]:
        return self.rows[:n]


def read_file(path: str | Path) -> RawTable:
    p = Path(path)
    if not p.exists():
        raise FileReadError(f"文件不存在: {p}")
    if p.stat().st_size == 0:
        raise EmptyDataError(f"文件为空: {p}")
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return _read_csv(p)
    if suffix in (".xlsx", ".xlsm"):
        return _read_xlsx(p)
    if suffix == ".jsonl" or suffix == ".ndjson":
        return _read_jsonl(p)
    if suffix == ".json":
        return _read_json(p)
    raise UnsupportedFormatError(f"不支持的格式: {suffix}（支持 csv/xlsx/json/jsonl）")


def _decode_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise FileReadError("无法解码文件（尝试 utf-8/gbk 均失败）")


def _read_csv(p: Path) -> RawTable:
    try:
        text = _decode_bytes(p.read_bytes())
    except FileReadError:
        raise
    except OSError as e:
        raise FileReadError(f"读取失败: {e}") from e
    try:
        reader = csv.DictReader(text.splitlines())
        cols = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    except csv.Error as e:
        raise FileReadError(f"CSV 解析失败: {e}") from e
    if not cols:
        raise EmptyDataError("CSV 无表头")
    if not rows:
        raise EmptyDataError("CSV 无数据行")
    return RawTable(columns=cols, rows=rows, source_path=str(p), format="csv")


def _read_xlsx(p: Path) -> RawTable:
    try:
        import openpyxl
    except ImportError as e:
        raise FileReadError("缺少 openpyxl，无法读取 xlsx") from e
    try:
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None)
        if header is None:
            raise EmptyDataError("XLSX 无表头")
        cols = [str(h) if h is not None else "" for h in header]
        rows: list[dict[str, Any]] = []
        for r in rows_iter:
            if r is None or all(v is None or str(v).strip() == "" for v in r):
                continue
            rows.append({cols[i]: ("" if i >= len(r) or r[i] is None else r[i]) for i in range(len(cols))})
        wb.close()
    except EmptyDataError:
        raise
    except Exception as e:  # openpyxl 对损坏文件抛多种异常
        raise FileReadError(f"XLSX 解析失败（文件可能损坏）: {e}") from e
    if not rows:
        raise EmptyDataError("XLSX 无数据行")
    return RawTable(columns=cols, rows=rows, source_path=str(p), format="xlsx")


def _read_jsonl(p: Path) -> RawTable:
    rows: list[dict[str, Any]] = []
    bad_lines: list[int] = []
    try:
        text = _decode_bytes(p.read_bytes())
    except OSError as e:
        raise FileReadError(f"读取失败: {e}") from e
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            bad_lines.append(i)
            continue
        if isinstance(obj, dict):
            rows.append(obj)
        else:
            bad_lines.append(i)
    if bad_lines and not rows:
        raise FileReadError(f"JSONL 全部行解析失败，首个坏行: {bad_lines[0]}")
    if not rows:
        raise EmptyDataError("JSONL 无有效数据行")
    cols = sorted({k for r in rows for k in r.keys()})
    t = RawTable(columns=cols, rows=rows, source_path=str(p), format="jsonl")
    if bad_lines:
        t.warnings.append(f"跳过 {len(bad_lines)} 个无法解析的行: 行号 {bad_lines[:10]}")
    return t


def _read_json(p: Path) -> RawTable:
    try:
        text = _decode_bytes(p.read_bytes())
    except OSError as e:
        raise FileReadError(f"读取失败: {e}") from e
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise FileReadError(f"JSON 解析失败: {e}") from e
    if isinstance(obj, list):
        rows = [r for r in obj if isinstance(r, dict)]
    elif isinstance(obj, dict) and isinstance(obj.get("data"), list):
        rows = [r for r in obj["data"] if isinstance(r, dict)]
    elif isinstance(obj, dict):
        rows = [obj]
    else:
        raise EmptyDataError("JSON 结构无法识别（期望对象数组或 {data: []}）")
    if not rows:
        raise EmptyDataError("JSON 无数据行")
    cols = sorted({k for r in rows for k in r.keys()})
    return RawTable(columns=cols, rows=rows, source_path=str(p), format="json")
