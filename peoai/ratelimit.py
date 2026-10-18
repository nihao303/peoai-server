"""限流：按 API Key / IP 的滑动窗口计数。

只做进程内限流（单实例足够）；多实例部署请改用 Redis。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple


class RateLimiter:
    """滑动窗口限流器：window 秒内最多 limit 次。"""

    def __init__(self, window_seconds: int = 60, max_identities: int = 4096) -> None:
        self.window = max(1, int(window_seconds))
        self.max_identities = max(16, int(max_identities))
        self._lock = threading.Lock()
        self._hits: Dict[str, Deque[float]] = {}

    def hit(self, identity: str, limit: int) -> Tuple[bool, int, int]:
        """记录一次请求，返回 (是否放行, 建议重试秒数, 剩余额度)。"""
        if not limit or limit <= 0:
            return True, 0, -1
        current = time.time()
        cutoff = current - self.window
        with self._lock:
            bucket = self._hits.get(identity)
            if bucket is None:
                if len(self._hits) >= self.max_identities:
                    self._evict_locked(cutoff)
                bucket = deque()
                self._hits[identity] = bucket
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry = max(1, int(bucket[0] + self.window - current) + 1)
                return False, retry, 0
            bucket.append(current)
            return True, 0, max(0, limit - len(bucket))

    def _evict_locked(self, cutoff: float) -> None:
        stale = [key for key, bucket in self._hits.items() if not bucket or bucket[-1] <= cutoff]
        for key in stale[: max(1, len(stale) // 2 or 1)]:
            self._hits.pop(key, None)
        if len(self._hits) >= self.max_identities:
            self._hits.clear()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
