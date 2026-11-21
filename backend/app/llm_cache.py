"""推荐结果缓存：只缓存「模型成功挑选」的结果。

降级结果（rules / timeout / invalid_ids）绝不入缓存——
否则一次抽风会被钉住半小时。key 里带 wardrobe_hash：
改任何一件衣服都会失效，这是有意的。
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass

MAX_ENTRIES = 200
DEFAULT_TTL_SECONDS = 30 * 60


@dataclass(frozen=True)
class CachedPick:
    item_ids: tuple[int, ...]
    reason: str
    attempts: int


_cache: dict[str, tuple[float, CachedPick]] = {}


def ttl_seconds() -> int:
    raw = os.environ.get("EW_LLM_CACHE_TTL", "").strip()
    try:
        return int(raw) if raw else DEFAULT_TTL_SECONDS
    except ValueError:
        return DEFAULT_TTL_SECONDS


def hash_weather(snapshot) -> str:  # noqa: ANN001
    payload = "|".join(
        str(value)
        for value in (
            snapshot.t_min,
            snapshot.t_max,
            snapshot.feels_min,
            snapshot.feels_max,
            snapshot.precip_prob,
            snapshot.weather_code,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def hash_wardrobe(rows) -> str:  # noqa: ANN001
    """未删单品的 id + updated_at；改任何一个字段都会变。"""
    payload = "|".join(f"{row.id}:{row.updated_at}" for row in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def build_key(
    *, date: str, occasion: str | None, weather_hash: str, wardrobe_hash: str, mode: str
) -> str:
    return "|".join((date, occasion or "", weather_hash, wardrobe_hash, mode))


def get(key: str) -> CachedPick | None:
    hit = _cache.get(key)
    if hit is None:
        return None
    stored_at, pick = hit
    if time.monotonic() - stored_at > ttl_seconds():
        _cache.pop(key, None)
        return None
    return pick


def put(key: str, pick: CachedPick) -> None:
    if len(_cache) >= MAX_ENTRIES and key not in _cache:
        oldest = min(_cache.items(), key=lambda item: item[1][0])
        _cache.pop(oldest[0], None)
    _cache[key] = (time.monotonic(), pick)


def clear() -> None:
    _cache.clear()


def size() -> int:
    return len(_cache)
