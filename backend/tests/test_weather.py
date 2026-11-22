"""天气接口测试：全程 monkeypatch httpx，不打真实网络。"""

from __future__ import annotations

import logging

import httpx
import pytest
from sqlalchemy import delete

from app import weather
from app.data.cities import CITIES, City
from app.db import SessionLocal
from app.models import WeatherSnapshotRow

# 上游返回样例：真实的双模型响应（2026-11-21 杭州实测）。
# 坐标故意与请求值不同（Open-Meteo 会把坐标吸附到网格），
# 用来证明缓存 key 不是拿响应值算的。
CMA = "cma_grapes_global"
BEST = "best_match"

UPSTREAM_OK = {
    "latitude": 30.2636,
    "longitude": 120.14051,
    "timezone": "Asia/Shanghai",
    "daily": {
        "time": ["2026-11-21"],
        f"temperature_2m_max_{CMA}": [14.6],
        f"temperature_2m_min_{CMA}": [6.8],
        f"apparent_temperature_max_{CMA}": [11.9],
        f"apparent_temperature_min_{CMA}": [4.1],
        f"precipitation_probability_max_{CMA}": [None],
        f"wind_speed_10m_max_{CMA}": [9.7],
        f"uv_index_max_{CMA}": [None],
        f"weather_code_{CMA}": [0],
        f"temperature_2m_max_{BEST}": [15.5],
        f"temperature_2m_min_{BEST}": [3.1],
        f"apparent_temperature_max_{BEST}": [13.2],
        f"apparent_temperature_min_{BEST}": [0.8],
        f"precipitation_probability_max_{BEST}": [0],
        f"wind_speed_10m_max_{BEST}": [6.5],
        f"uv_index_max_{BEST}": [4.45],
        f"weather_code_{BEST}": [0],
    },
}


class FakeResponse:
    def __init__(self, payload: dict | None = None, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeClient:
    """替代 httpx.AsyncClient：记录调用次数，按需返回或抛错。"""

    calls = 0
    response: FakeResponse | None = None
    error: Exception | None = None
    # 按顺序消费：元素是异常就抛，是响应就返回；空了回落到 error/response
    queue: list[object] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url, params=None):
        FakeClient.calls += 1
        if FakeClient.queue:
            item = FakeClient.queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if FakeClient.error is not None:
            raise FakeClient.error
        assert FakeClient.response is not None
        return FakeClient.response


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    weather.clear_cache()
    weather.clear_cooldown()
    FakeClient.calls = 0
    FakeClient.response = FakeResponse(UPSTREAM_OK)
    FakeClient.error = None
    FakeClient.queue = []
    monkeypatch.setattr(weather.httpx, "AsyncClient", FakeClient)
    # 重试间隔归零，测试不要真的睡
    monkeypatch.setattr(weather, "RETRY_DELAY_SECONDS", 0)
    # 清掉落盘快照，否则「无缓存 → 502」的用例会被上一条测试写下的快照兜住
    with SessionLocal() as db:
        db.execute(delete(WeatherSnapshotRow))
        db.commit()
    yield FakeClient
    weather.clear_cache()
    weather.clear_cooldown()


def test_weather_fields_and_types(client):
    res = client.get("/api/weather", params={"city": "杭州"})
    assert res.status_code == 200, res.text

    body = res.json()
    expected = {
        "city",
        "date",
        "t_min",
        "t_max",
        "feels_min",
        "feels_max",
        "precip_prob",
        "wind",
        "uv",
        "weather_code",
        "weather_text",
        "observed_at",
        "fetched_at",
        "cached",
        "stale",
    }
    assert set(body) == expected

    for key in ("t_min", "t_max", "feels_min", "feels_max", "precip_prob", "wind", "uv"):
        assert isinstance(body[key], float), key

    assert body["city"] == "杭州"
    assert body["date"] == weather.today_in("Asia/Shanghai")
    assert body["cached"] is False
    assert body["stale"] is False


def test_dual_model_picks_cma_for_temperature_and_best_for_probability(client):
    body = client.get("/api/weather", params={"city": "杭州"}).json()

    # 温度/体感来自 CMA
    assert body["t_min"] == pytest.approx(6.8)
    assert body["t_max"] == pytest.approx(14.6)
    assert body["feels_min"] == pytest.approx(4.1)
    assert body["feels_max"] == pytest.approx(11.9)
    assert body["wind"] == pytest.approx(9.7)

    # CMA 这两个字段是 null，必须落到 best_match
    assert body["precip_prob"] == pytest.approx(0)
    assert body["uv"] == pytest.approx(4.45)

    assert body["weather_code"] == 0
    assert body["weather_text"] == "晴"


def test_missing_cma_temperature_falls_back_to_best_match(client, fake_http):
    payload = {
        **UPSTREAM_OK,
        "daily": {
            key: value
            for key, value in UPSTREAM_OK["daily"].items()
            if not key.endswith(f"_{CMA}") or "precipitation" in key or "uv_index" in key
        },
    }
    fake_http.response = FakeResponse(payload=payload)

    res = client.get("/api/weather", params={"city": "杭州"})
    assert res.status_code == 200, res.text

    body = res.json()
    assert body["t_min"] == pytest.approx(3.1)
    assert body["t_max"] == pytest.approx(15.5)
    assert body["feels_min"] == pytest.approx(0.8)
    assert body["feels_max"] == pytest.approx(13.2)


def test_missing_field_in_both_models_returns_502(client, fake_http):
    payload = {
        **UPSTREAM_OK,
        "daily": {
            key: value
            for key, value in UPSTREAM_OK["daily"].items()
            if not key.startswith("temperature_2m_min")
        },
    }
    fake_http.response = FakeResponse(payload=payload)

    res = client.get("/api/weather", params={"city": "杭州"})
    assert res.status_code == 502
    assert res.json()["detail"]["code"] == "weather_upstream_failed"


def test_default_city_is_hangzhou(client):
    res = client.get("/api/weather")
    assert res.status_code == 200
    assert res.json()["city"] == "杭州"


def test_second_call_hits_cache(client, fake_http):
    first = client.get("/api/weather", params={"city": "上海"}).json()
    second = client.get("/api/weather", params={"city": "上海"}).json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert second["stale"] is False
    assert fake_http.calls == 1  # 第二次没有打上游
    assert second["t_max"] == pytest.approx(first["t_max"])


def test_unknown_city_returns_400(client):
    res = client.get("/api/weather", params={"city": "瞎编城市"})
    assert res.status_code == 400
    assert "瞎编城市" in res.json()["detail"]


# --- 超时重试（N5b） ------------------------------------------------------


def test_timeout_then_success_retries_once(client, fake_http, caplog):
    fake_http.queue = [httpx.ConnectTimeout("boom"), FakeResponse(UPSTREAM_OK)]

    with caplog.at_level(logging.WARNING):
        res = client.get("/api/weather", params={"city": "杭州"})

    assert res.status_code == 200
    assert res.json()["cached"] is False
    assert res.json()["city"] == "杭州"
    assert fake_http.calls == 2
    assert "weather retry city=杭州 attempt=2" in "\n".join(
        record.getMessage() for record in caplog.records
    )


def test_two_timeouts_return_502(client, fake_http):
    fake_http.queue = [httpx.ConnectTimeout("boom"), httpx.ReadTimeout("again")]

    res = client.get("/api/weather", params={"city": "杭州"})

    assert res.status_code == 502
    assert res.json()["detail"]["code"] == "weather_upstream_failed"
    assert fake_http.calls == 2


def test_http_400_is_not_retried(client, fake_http):
    fake_http.queue = [FakeResponse(status_code=400)]

    res = client.get("/api/weather", params={"city": "杭州"})

    assert res.status_code == 502
    assert fake_http.calls == 1


def test_http_500_is_not_retried(client, fake_http):
    fake_http.queue = [FakeResponse(status_code=500)]

    res = client.get("/api/weather", params={"city": "杭州"})

    assert res.status_code == 502
    assert fake_http.calls == 1


def test_upstream_failure_with_cache_returns_stale(client, fake_http, monkeypatch):
    # 先成功一次，把结果放进缓存
    assert client.get("/api/weather", params={"city": "杭州"}).status_code == 200

    # 让缓存立刻过期，但成功结果仍留在 dict 里
    monkeypatch.setattr(weather, "CACHE_TTL_SECONDS", -1)
    fake_http.error = httpx.ConnectError("boom")

    res = client.get("/api/weather", params={"city": "杭州"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["stale"] is True
    assert body["cached"] is True
    assert body["city"] == "杭州"


def test_upstream_failure_without_cache_returns_502(client, fake_http):
    fake_http.error = httpx.ConnectError("boom")

    res = client.get("/api/weather", params={"city": "杭州"})
    assert res.status_code == 502
    detail = res.json()["detail"]
    assert detail["code"] == "weather_upstream_failed"


def test_upstream_non_200_returns_502(client, fake_http):
    fake_http.response = FakeResponse(status_code=500)

    res = client.get("/api/weather", params={"city": "北京"})
    assert res.status_code == 502
    assert res.json()["detail"]["code"] == "weather_upstream_failed"


def test_broken_payload_returns_502(client, fake_http):
    fake_http.response = FakeResponse(payload={"daily": {"temperature_2m_max": []}})

    res = client.get("/api/weather", params={"city": "成都"})
    assert res.status_code == 502


# --- 坐标 golden 测试：钉死「纬度在前、经度在后」 -------------------------


def test_hangzhou_is_lat_then_lon():
    city = CITIES["杭州"]
    assert city.latitude == pytest.approx(30.274, abs=1)
    assert city.longitude == pytest.approx(120.155, abs=1)
    # 中国城市的纬度不可能有三位数
    assert city.latitude < 90
    assert city.longitude > 90


def test_all_cities_have_valid_latitude():
    for name, city in CITIES.items():
        assert -90.0 <= city.latitude <= 90.0, f"{name} 纬度越界：{city.latitude}"
        assert -180.0 <= city.longitude <= 180.0, f"{name} 经度越界：{city.longitude}"


def test_reversed_coordinates_fail_at_construction():
    """把经纬度写反必须在构造时就炸，而不是等上游 400。"""
    with pytest.raises(ValueError, match="纬度越界"):
        City("写反了", 120.155, 30.274, "Asia/Shanghai")


def test_upstream_params_use_city_latitude():
    """请求参数里的 latitude 必须是城市纬度，不能是经度。"""
    city = CITIES["杭州"]
    params = weather._params(city)

    assert params["latitude"] == city.latitude
    assert params["longitude"] == city.longitude
    assert params["latitude"] == pytest.approx(30.274, abs=0.01)
    assert params["longitude"] == pytest.approx(120.155, abs=0.01)
    assert -90 <= float(params["latitude"]) <= 90
    assert params["timezone"] == "Asia/Shanghai"
    assert params["forecast_days"] == 1
    assert params["daily"] == ",".join(weather.DAILY_FIELDS)


def test_params_request_both_models():
    """参数层 golden：一次请求要两个模型，缺一个就少一半字段。"""
    params = weather._params(CITIES["杭州"])
    assert params["models"] == "cma_grapes_global,best_match"
    assert "weather_code" in str(params["daily"])
    assert "uv_index_max" in str(params["daily"])


@pytest.mark.parametrize(
    ("code", "text"),
    [
        (0, "晴"),
        (1, "多云"),
        (3, "阴"),
        (45, "雾"),
        (53, "毛毛雨"),
        (63, "雨"),
        (73, "雪"),
        (81, "阵雨"),
        (96, "雷雨"),
        (123, "未知"),
    ],
)
def test_weather_text_mapping(code, text):
    assert weather.weather_text(code) == text


# --- 推荐接口的契约（天气用假上游，规则本身在 test_rules.py） ---------------


def test_recommend_endpoint_shape(client, fake_http):
    res = client.get("/api/recommend", params={"occasion": "casual"})
    assert res.status_code == 200, res.text

    body = res.json()
    assert set(body) == {
        "date",
        "weather",
        "outfits",
        "notice",
        "source",
        "attempts",
        "fallback_reason",
        "cached",
    }
    assert body["date"] == body["weather"]["date"]
    assert len(body["outfits"]) <= 3
    assert body["source"] == "rules"
    assert body["attempts"] == 0

    for outfit in body["outfits"]:
        assert outfit["reason"]
        assert outfit["items"]
        for item in outfit["items"]:
            assert set(item) == {"id", "category", "warmth", "layer", "thumb_url"}


def test_recommend_endpoint_propagates_weather_errors(client, fake_http):
    fake_http.error = httpx.ConnectError("boom")
    weather.clear_cache()
    weather.clear_cooldown()

    res = client.get("/api/recommend", params={"city": "杭州"})
    assert res.status_code == 502
    assert res.json()["detail"]["code"] == "weather_upstream_failed"
