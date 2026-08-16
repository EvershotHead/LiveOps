"""令牌桶限速：间隔式（相邻请求最小间隔），时钟可注入便于测试。"""

from __future__ import annotations

import time
from typing import Callable


class TokenBucket:
    """min_interval 秒内最多 1 次请求；wait=True 时 sleep 到可用。"""

    def __init__(self, min_interval: float, clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep):
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleeper
        self._last = float("-inf")

    def acquire(self, *, wait: bool = True) -> float:
        """返回等待秒数（wait=False 时不等待，间隔不足返回需等待的秒数）。"""
        now = self._clock()
        ready_at = self._last + self.min_interval
        if now >= ready_at:
            self._last = now
            return 0.0
        need = ready_at - now
        if wait:
            self._sleep(need)
            self._last = self._clock()
            return need
        return need

    def would_block(self) -> bool:
        return self._clock() < self._last + self.min_interval
