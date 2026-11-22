"""天气上游失败的短冷却：避免每个请求都白等两次超时。"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import delete

from app import weather
from app.db import SessionLocal
from app.models import WeatherSnapshotRow

from .test_weather import UPSTREAM_OK


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
    calls = 0
    fail = False

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        FakeClient.calls += 1
        if FakeClient.fail:
            raise httpx.ConnectTimeout("boom")
        return FakeResponse({"daily": UPSTREAM_OK["daily"]})


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    weather.clear_cache()
    weather.clear_cooldown()
    FakeClient.calls = 0
    FakeClient.fail = False
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(weather, "RETRY_DELAY_SECONDS", 0)
    monkeypatch.delenv("EW_WEATHER_COOLDOWN_SECONDS", raising=False)
    with SessionLocal() as db:
        db.execute(delete(WeatherSnapshotRow))
        db.commit()
    yield
    weather.clear_cache()
    weather.clear_cooldown()


def seed_snapshot(client) -> None:
    res = client.get("/api/weather", params={"city": "杭州"})
    assert res.status_code == 200 and res.json()["stale"] is False
    weather.clear_cache()  # 模拟进程重启：内存没了，DB 还在


def test_second_request_skips_upstream_in_cooldown(client):
    seed_snapshot(client)
    FakeClient.fail = True

    first = client.get("/api/weather", params={"city": "杭州"})
    assert first.status_code == 200 and first.json()["stale"] is True
    calls_after_failure = FakeClient.calls
    assert calls_after_failure >= 1

    second = client.get("/api/weather", params={"city": "杭州"})

    assert second.status_code == 200
    assert second.json()["stale"] is True
    assert FakeClient.calls == calls_after_failure  # 冷却期不打上游


def test_recovered_upstream_is_not_retried_during_cooldown(client):
    seed_snapshot(client)
    FakeClient.fail = True
    client.get("/api/weather", params={"city": "杭州"})
    calls = FakeClient.calls

    FakeClient.fail = False  # 上游其实已经好了
    res = client.get("/api/weather", params={"city": "杭州"})

    assert res.status_code == 200
    assert res.json()["stale"] is True
    assert FakeClient.calls == calls  # 60 秒后自然恢复，冷却期内不试


def test_cooldown_does_not_hide_missing_data(client):
    """没有任何兜底数据时必须继续试上游，否则首次请求永远 502。"""
    FakeClient.fail = True
    first = client.get("/api/weather", params={"city": "杭州"})
    assert first.status_code == 502
    calls = FakeClient.calls

    second = client.get("/api/weather", params={"city": "杭州"})

    assert second.status_code == 502
    assert FakeClient.calls > calls  # 仍然打了上游


def test_cooldown_is_configurable(monkeypatch):
    monkeypatch.setenv("EW_WEATHER_COOLDOWN_SECONDS", "0")
    assert weather.cooldown_seconds() == 0

    monkeypatch.setenv("EW_WEATHER_COOLDOWN_SECONDS", "abc")
    assert weather.cooldown_seconds() == weather.DEFAULT_COOLDOWN_SECONDS

    monkeypatch.delenv("EW_WEATHER_COOLDOWN_SECONDS")
    assert weather.cooldown_seconds() == weather.DEFAULT_COOLDOWN_SECONDS


def test_success_clears_cooldown(client):
    seed_snapshot(client)
    FakeClient.fail = True
    client.get("/api/weather", params={"city": "杭州"})
    assert weather.in_cooldown() is True

    weather.clear_cache()
    weather.clear_cooldown()
    FakeClient.fail = False
    res = client.get("/api/weather", params={"city": "杭州"})

    assert res.json()["stale"] is False
    assert weather.in_cooldown() is False
