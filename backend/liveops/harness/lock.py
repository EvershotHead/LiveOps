"""单机单任务文件锁：同一时刻只允许一个分析任务运行。"""

from __future__ import annotations

import os
from pathlib import Path

import portalocker


class RunLockError(Exception):
    """已有任务在运行（HTTP 层映射为 409）。"""


class RunLock:
    def __init__(self, lock_path: str | Path):
        self.path = Path(lock_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = None

    def __enter__(self):
        try:
            self._fh = open(self.path, "a+")
            portalocker.lock(self._fh, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except (portalocker.AlreadyLocked, OSError):
            if self._fh:
                self._fh.close()
                self._fh = None
            raise RunLockError(f"已有分析任务在运行（锁: {self.path}）")
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(f"pid={os.getpid()}\n")
        self._fh.flush()
        return self

    def __exit__(self, *exc):
        if self._fh:
            try:
                portalocker.unlock(self._fh)
            finally:
                self._fh.close()
                self._fh = None
        return False
