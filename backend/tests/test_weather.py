"""天气接口测试：全程 monkeypatch httpx，不打真实网络。"""

from __future__ import annotations

import httpx
import pytest

from app import weather
from app.data.cities import CITIES, City

# 上游返回样例。坐标故意与请求值不同（Open-Meteo 会把坐标吸附到网格），
# 用来证明缓存 key 不是拿响应值算的。
UPSTREAM_OK = {
    "latitude": 30.2636,
    "longitude": 120.1,
    "timezone": "Asia/Shanghai",
    "daily": {
        "time": ["2026-11-21"],
        "temperature_2m_max": [21.5],
        "temperature_2m_min": [12.3],
        "apparent_temperature_max": [20.8],
        "apparent_temperature_min": [10.9],
        "precipitation_probability_max": [10],
        "wind_speed_10m_max": [12.4],
        "uv_index_max": [3.2],
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

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url, params=None):
        FakeClient.calls += 1
        if FakeClient.error is not None:
            raise FakeClient.error
        assert FakeClient.response is not None
        return FakeClient.response


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    weather.clear_cache()
    FakeClient.calls = 0
    FakeClient.response = FakeResponse(UPSTREAM_OK)
    FakeClient.error = None
    monkeypatch.setattr(weather.httpx, "AsyncClient", FakeClient)
    yield FakeClient
    weather.clear_cache()


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
