"""W5d：天气快照落盘与三级降级。全 mock 上游，不联网。"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import delete, select

from app import db as db_module
from app import weather
from app.data.cities import CITIES
from app.db import SessionLocal
from app.models import WeatherSnapshotRow

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
        return FakeResponse({"daily": WEATHER_DAILY})


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    weather.clear_cache()
    weather.clear_cooldown()
    FakeClient.calls = 0
    FakeClient.fail = False
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(weather, "RETRY_DELAY_SECONDS", 0)
    with SessionLocal() as db:
        db.execute(delete(WeatherSnapshotRow))
        db.commit()
    yield FakeClient
    weather.clear_cache()
    weather.clear_cooldown()


def snapshots() -> list[WeatherSnapshotRow]:
    with SessionLocal() as db:
        return list(db.execute(select(WeatherSnapshotRow)).scalars().all())


def test_success_writes_snapshot_row(client):
    res = client.get("/api/weather", params={"city": "杭州"})
    assert res.status_code == 200
    body = res.json()
    assert body["stale"] is False
    assert body["observed_at"] == body["date"]
    assert body["fetched_at"]

    rows = snapshots()
    assert len(rows) == 1
    assert rows[0].city_name == "杭州"
    assert rows[0].observed_at == body["date"]
    assert "temperature_2m_min" not in rows[0].payload  # 存的是解析后的快照字段


def test_success_updates_existing_row(client):
    client.get("/api/weather", params={"city": "杭州"})
    first_fetched = snapshots()[0].fetched_at

    weather.clear_cache()
    weather.clear_cooldown()
    client.get("/api/weather", params={"city": "杭州"})

    rows = snapshots()
    assert len(rows) == 1  # 同城覆盖，不新增
    assert rows[0].fetched_at >= first_fetched


def test_upstream_failure_falls_back_to_db_snapshot(client):
    # 先成功一次，落盘
    client.get("/api/weather", params={"city": "杭州"})
    saved = snapshots()[0]
    weather.clear_cache()
    weather.clear_cooldown()  # 模拟重启：内存没了，DB 还在

    FakeClient.fail = True
    res = client.get("/api/weather", params={"city": "杭州"})

    assert res.status_code == 200
    body = res.json()
    assert body["stale"] is True
    assert body["observed_at"] == saved.observed_at
    assert body["fetched_at"] == saved.fetched_at
    assert body["t_min"] == pytest.approx(6.8)


def test_upstream_failure_without_snapshot_returns_502(client):
    FakeClient.fail = True
    res = client.get("/api/weather", params={"city": "杭州"})
    assert res.status_code == 502


def test_recommend_still_works_from_db_snapshot(client):
    client.get("/api/weather", params={"city": "杭州"})
    weather.clear_cache()
    weather.clear_cooldown()
    FakeClient.fail = True

    res = client.get("/api/recommend", params={"mode": "rules"})
    assert res.status_code == 200
    body = res.json()
    assert body["weather"]["stale"] is True
    assert len(body["outfits"]) >= 1


def test_snapshot_write_failure_does_not_break_weather(client, monkeypatch):
    class BrokenSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return None

        def add(self, *args, **kwargs):
            pass

        def commit(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(db_module, "SessionLocal", lambda: BrokenSession())

    res = client.get("/api/weather", params={"city": "上海"})

    assert res.status_code == 200
    assert res.json()["stale"] is False


def test_weather_url_is_configurable(monkeypatch):
    monkeypatch.setenv("EW_WEATHER_URL", "http://127.0.0.1:9")
    assert weather.api_url() == "http://127.0.0.1:9/v1/forecast"

    monkeypatch.delenv("EW_WEATHER_URL")
    assert weather.api_url().startswith("https://api.open-meteo.com/v1/forecast")
