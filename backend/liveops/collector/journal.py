"""采集日志与断点：JSONL journal，每 N 条 fsync，重启续采不重复。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class JournalEntry:
    at: str
    kind: str          # search | meta | comment | hard_stop | info
    url: str = ""
    page: int = 0
    items: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


class CollectionJournal:
    """追加式日志。断点 = 已采集的 (video_id, 模式, 页码) 集合。"""

    def __init__(self, path: str | Path, flush_every: int = 50):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a", encoding="utf-8")
        self._since_flush = 0
        self.flush_every = flush_every
        self.collected_pages: set[tuple[str, str, int]] = set()
        self.post_ids: set[str] = set()
        self.entries: list[JournalEntry] = []
        self._load_existing()

    def _load_existing(self) -> None:
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 半行（崩溃残留）忽略，从上一完整条续
                self.entries.append(JournalEntry(**e))
                d = e.get("detail", {})
                key = (d.get("video_id", ""), d.get("mode", ""), e.get("page", 0))
                if d.get("video_id") and e.get("kind") == "comment":
                    self.collected_pages.add(key)
                    for pid in d.get("post_ids", []):
                        self.post_ids.add(pid)

    def has_page(self, video_id: str, mode: str, page: int) -> bool:
        return (video_id, mode, page) in self.collected_pages

    def log(self, kind: str, *, url: str = "", page: int = 0, items: int = 0, **detail: Any) -> None:
        e = JournalEntry(
            at=datetime.now(timezone.utc).isoformat(), kind=kind, url=url,
            page=page, items=items, detail=detail,
        )
        self._fh.write(json.dumps(e.__dict__, ensure_ascii=False) + "\n")
        self.entries.append(e)
        if kind == "comment" and detail.get("video_id"):
            self.collected_pages.add((detail["video_id"], detail.get("mode", ""), page))
            self.post_ids.update(detail.get("post_ids", []))
        self._since_flush += 1
        if self._since_flush >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self._since_flush = 0

    def close(self) -> None:
        self.flush()
        self._fh.close()
