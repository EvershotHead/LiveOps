"""SQLite 响应缓存：key = sha256(model + prompt_version + messages)。

保证同配置重跑零额外成本，且结果可复现。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS response_cache (
    cache_key TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def cache_key(model: str, prompt_version: str, messages: list[dict[str, str]]) -> str:
    payload = json.dumps(
        {"model": model, "pv": prompt_version, "messages": messages},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT response FROM response_cache WHERE cache_key=?", (key,)
            ).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return row[0]

    def put(self, key: str, model: str, prompt_version: str, response: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO response_cache (cache_key, model, prompt_version, response)"
                " VALUES (?,?,?,?)",
                (key, model, prompt_version, response),
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class NullCache(ResponseCache):
    """测试用：不落盘。"""

    def __init__(self):  # noqa: super 不连接
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> str | None:
        self.misses += 1
        return None

    def put(self, key: str, model: str, prompt_version: str, response: str) -> None:
        return None

    def close(self) -> None:
        return None
