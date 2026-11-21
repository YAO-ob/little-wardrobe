"""N6 测试：指标落库 + /api/metrics 聚合。全 mock 上游，不打网络。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import delete, select

from app import limits, llm_cache, weather
from app.db import SessionLocal
from app.models import LlmMetric

WEATHER_DAILY = {
    "time": ["2026-11-21"],
    "temperature_2m_max_cma_grapes_global": [14.6],
    "temperature_2m_min_cma_grapes_global": [6.8],
    "apparent_temperature_max_cma_grapes_global": [11.9],
    "apparent_temperature_min_cma_grapes_global": [4.1],
    "precipitation_probability_max_cma_grapes_global": [None],
    "wind_speed_10m_max_cma_grapes_global": [9.7],
    "uv_index_max_cma_grapes_global": [None],
    "weather_code_cma_grapes_global": [0],
    "temperature_2m_max_best_match": [15.5],
    "temperature_2m_min_best_match": [3.1],
    "apparent_temperature_max_best_match": [13.2],
    "apparent_temperature_min_best_match": [0.8],
    "precipitation_probability_max_best_match": [0],
    "wind_speed_10m_max_best_match": [6.5],
    "uv_index_max_best_match": [4.45],
    "weather_code_best_match": [0],
}


class FakeResponse:
    def __init__(self, payload: dict | None = None, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeClient:
    chat_queue: list[object] = []
    chat_calls = 0

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        return FakeResponse({"daily": WEATHER_DAILY})

    async def post(self, url, json=None, headers=None):
        FakeClient.chat_calls += 1
        item = FakeClient.chat_queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def llm_reply(item_ids: list[int], prompt_tokens: int = 82, completion_tokens: int = 15):
    return FakeResponse(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"item_ids": item_ids, "reason": "模型选的"})
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        }
    )


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    weather.clear_cache()
    llm_cache.clear()
    limits.clear()
    FakeClient.chat_queue = []
    FakeClient.chat_calls = 0
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.delenv("EW_LLM_KEY", raising=False)
    monkeypatch.delenv("EW_LLM_RATE_LIMIT_PER_MIN", raising=False)
    monkeypatch.delenv("EW_LLM_CACHE_TTL", raising=False)

    with SessionLocal() as db:
        db.execute(delete(LlmMetric))
        db.commit()
    yield FakeClient
    weather.clear_cache()


def ensure_wardrobe(client) -> None:
    items = client.get("/api/items", params={"limit": 500}).json()["items"]
    neutral = {item["category"] for item in items if not item["occasion"]}
    for category in ("top", "bottom", "shoes", "outer"):
        if category not in neutral:
            client.post("/api/items", json={"category": category})


def rows() -> list[LlmMetric]:
    with SessionLocal() as db:
        return list(db.execute(select(LlmMetric).order_by(LlmMetric.id)).scalars().all())


def metrics(client, days: int = 7) -> dict:
    return client.get("/api/metrics", params={"days": days}).json()


HEADERS = {"X-LLM-Key": "sk-test-secret"}


def _first_outfit_ids(client) -> list[int]:
    rec = client.get("/api/recommend", params={"mode": "rules"}).json()
    return [item["id"] for item in rec["outfits"][0]["items"]]


def test_success_writes_row_with_tokens(client):
    ensure_wardrobe(client)
    ids = _first_outfit_ids(client)
    FakeClient.chat_queue = [llm_reply(ids)]

    res = client.get("/api/recommend", params={"mode": "llm"}, headers=HEADERS)
    assert res.status_code == 200

    recorded = rows()
    assert len(recorded) == 1
    row = recorded[0]
    assert row.mode == "llm"
    assert row.source == "llm"
    assert row.cached is False
    assert row.attempts == 1
    assert row.fallback_reason is None
    assert row.model == "deepseek-chat"
    assert row.tokens_prompt == 82
    assert row.tokens_completion == 15
    assert row.is_byok is True
    assert row.latency_ms >= 0


def test_fallback_writes_row(client):
    ensure_wardrobe(client)
    FakeClient.chat_queue = [FakeResponse(status_code=429)]

    client.get("/api/recommend", params={"mode": "llm"}, headers=HEADERS)

    row = rows()[0]
    assert row.source == "rules"
    assert row.fallback_reason == "rate_limited"
    assert row.attempts == 1
    assert row.tokens_prompt is None


def test_no_key_writes_row(client):
    ensure_wardrobe(client)
    client.get("/api/recommend", params={"mode": "llm"})

    row = rows()[0]
    assert row.source == "rules"
    assert row.fallback_reason == "no_key"
    assert row.attempts == 0
    assert row.model is None
    assert row.is_byok is False


def test_cache_hit_writes_row(client):
    ensure_wardrobe(client)
    ids = _first_outfit_ids(client)
    FakeClient.chat_queue = [llm_reply(ids)]
    client.get("/api/recommend", params={"mode": "llm"}, headers=HEADERS)
    client.get("/api/recommend", params={"mode": "llm"}, headers=HEADERS)

    recorded = rows()
    assert len(recorded) == 2
    assert recorded[0].cached is False
    assert recorded[1].cached is True
    assert recorded[1].attempts == 0  # 命中缓存没有真的调模型
    assert FakeClient.chat_calls == 1


def test_metric_write_failure_does_not_break_response(client, monkeypatch):
    ensure_wardrobe(client)
    ids = _first_outfit_ids(client)
    FakeClient.chat_queue = [llm_reply(ids)]

    from sqlalchemy.orm import Session

    def boom(self, *args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(Session, "commit", boom)

    res = client.get("/api/recommend", params={"mode": "llm"}, headers=HEADERS)
    assert res.status_code == 200
    assert res.json()["source"] == "llm"


def test_metrics_aggregates_match_inserted_rows(client):
    now = datetime.now(timezone.utc)

    def make(**kwargs):
        defaults = dict(
            created_at=now.isoformat(timespec="seconds"),
            mode="llm",
            source="llm",
            cached=False,
            attempts=1,
            fallback_reason=None,
            latency_ms=100,
            model="deepseek-chat",
            tokens_prompt=80,
            tokens_completion=20,
            is_byok=True,
        )
        defaults.update(kwargs)
        return LlmMetric(**defaults)

    old = (now - timedelta(days=30)).isoformat(timespec="seconds")
    with SessionLocal() as db:
        db.add_all(
            [
                make(latency_ms=100),
                make(latency_ms=200),
                make(latency_ms=300),
                make(latency_ms=400),
                make(
                    source="rules",
                    fallback_reason="rate_limited",
                    attempts=0,
                    tokens_prompt=None,
                    tokens_completion=None,
                    is_byok=False,
                ),
                make(cached=True, attempts=0, tokens_prompt=None, tokens_completion=None),
                make(created_at=old, latency_ms=9999),  # 30 天前，days=7 不该算
            ]
        )
        db.commit()

    body = metrics(client, days=7)

    assert body["days"] == 7
    assert body["total_calls"] == 6
    assert body["llm_success"] == 4  # source=llm 且 cached=false
    assert body["cache_hits"] == 1
    assert body["fallbacks"] == 1
    assert body["fallback_by_reason"] == {"rate_limited": 1}
    # 只有 attempts>0 的 4 行算模型调用
    assert body["by_model"] == {"deepseek-chat": 4}
    assert body["tokens"] == {"prompt": 4 * 80, "completion": 4 * 20}
    assert body["byok_calls"] == 5
    assert body["server_key_calls"] == 1
    assert body["latency_ms"]["avg"] == 200.0  # (100+200+300+400+100+100)/6
    assert body["latency_ms"]["p50"] >= 100
    assert body["latency_ms"]["p95"] >= body["latency_ms"]["p50"]
    # 模型调用耗时只取 attempts>0 的四行
    assert body["model_latency_ms"]["avg"] == 250.0  # (100+200+300+400)/4
    assert body["model_latency_ms"]["p95"] >= body["model_latency_ms"]["p50"]

    # days=1 会把 7 天内的行也算进去（都是刚写的），但 30 天前那行依旧不算
    assert metrics(client, days=1)["total_calls"] == 6


def test_by_model_counts_only_real_calls_and_model_latency(client):
    """缓存命中与降级虽然带 model 名，但 attempts=0，不能算进 by_model。"""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def row(attempts: int, latency_ms: int, **kwargs):
        return LlmMetric(
            created_at=now,
            mode="llm",
            source=kwargs.pop("source", "llm"),
            cached=kwargs.pop("cached", False),
            attempts=attempts,
            fallback_reason=kwargs.pop("fallback_reason", None),
            latency_ms=latency_ms,
            model="deepseek-chat",
            tokens_prompt=100 if attempts else None,
            tokens_completion=20 if attempts else None,
            is_byok=True,
        )

    with SessionLocal() as db:
        db.add_all(
            [
                row(0, 2, cached=True),  # 缓存命中
                row(1, 800),  # 真实调用
                row(0, 3, source="rules", fallback_reason="rate_limited"),  # 降级
            ]
        )
        db.commit()

    body = metrics(client)

    assert body["by_model"] == {"deepseek-chat": 1}
    assert body["llm_success"] == 1
    assert body["model_latency_ms"]["avg"] == 800.0
    assert body["model_latency_ms"]["p50"] == 800
    assert body["model_latency_ms"]["p95"] == 800
    assert body["latency_ms"]["avg"] == 268.3  # (2+800+3)/3


def test_model_latency_is_null_when_no_model_calls(client):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with SessionLocal() as db:
        db.add(
            LlmMetric(
                created_at=now,
                mode="llm",
                source="rules",
                cached=False,
                attempts=0,
                fallback_reason="no_key",
                latency_ms=2,
                model=None,
                tokens_prompt=None,
                tokens_completion=None,
                is_byok=False,
            )
        )
        db.commit()

    body = metrics(client)

    assert body["by_model"] == {}
    assert body["model_latency_ms"] == {"avg": None, "p50": None, "p95": None}
    assert body["latency_ms"]["avg"] == 2.0


def test_metrics_days_validation(client):
    assert client.get("/api/metrics", params={"days": 0}).status_code == 422
    assert client.get("/api/metrics", params={"days": 91}).status_code == 422
