"""按客户端的分钟级滑动窗口限流。

只给「真的要调模型」的请求计数：命中缓存不算、mode=rules 不算。
超限不返回 429——页面永不因为后端限制挂掉，调用方退化成规则结果即可。
"""

from __future__ import annotations

import os
import time
from collections import deque

WINDOW_SECONDS = 60
DEFAULT_LIMIT_PER_MIN = 10
# 键超过这个数就顺手清一遍过期窗口，避免 dict 无限增长
_SWEEP_THRESHOLD = 500

_buckets: dict[str, deque[float]] = {}


def limit_per_min() -> int:
    raw = os.environ.get("EW_LLM_RATE_LIMIT_PER_MIN", "").strip()
    try:
        value = int(raw) if raw else DEFAULT_LIMIT_PER_MIN
    except ValueError:
        value = DEFAULT_LIMIT_PER_MIN
    return max(1, value)


def client_key(forwarded_for: str | None, client_host: str | None) -> str:
    if forwarded_for:
        # X-Forwarded-For 可能是逗号分隔的链路，取第一个（最靠近客户端的）
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    return client_host or "unknown"


def _prune(bucket: deque[float], now: float) -> None:
    while bucket and now - bucket[0] >= WINDOW_SECONDS:
        bucket.popleft()


def _sweep(now: float) -> None:
    if len(_buckets) < _SWEEP_THRESHOLD:
        return
    for key in [key for key, bucket in _buckets.items() if not bucket]:
        _buckets.pop(key, None)
    for key, bucket in list(_buckets.items()):
        _prune(bucket, now)
        if not bucket:
            _buckets.pop(key, None)


def remaining(key: str, limit: int | None = None) -> int:
    limit = limit if limit is not None else limit_per_min()
    bucket = _buckets.get(key)
    if not bucket:
        return limit
    now = time.monotonic()
    _prune(bucket, now)
    return max(0, limit - len(bucket))


def try_consume(key: str, limit: int | None = None) -> tuple[bool, int]:
    """尝试占用一次额度，返回 (是否放行, 剩余次数)。放行时才真的记账。"""
    limit = limit if limit is not None else limit_per_min()
    now = time.monotonic()
    _sweep(now)

    bucket = _buckets.setdefault(key, deque())
    _prune(bucket, now)

    if len(bucket) >= limit:
        return False, 0

    bucket.append(now)
    return True, max(0, limit - len(bucket))


def clear() -> None:
    _buckets.clear()
