"""天气服务：Open-Meteo 日预报 + 进程内缓存 + 失败降级。

只做「取今天这一天」，不做多日预报、不做多时区换算。
缓存 key 用请求坐标（保留 3 位小数）+ 城市本地日期，**不用响应里的坐标**：
Open-Meteo 会把坐标吸附到网格（传 30.2741 可能返回 30.263618），
拿响应值当 key 会让缓存永远命中不了。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .data.cities import City, find_city

logger = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 5.0
# TLS 握手偶发超时：重试一次，间隔半秒
RETRY_DELAY_SECONDS = 0.5
CACHE_TTL_SECONDS = 2 * 60 * 60  # 2 小时，写死

# 双模型取数：CMA（中国气象局）更贴合国内实况，但不提供降水概率和 UV，
# 所以温度类走 CMA、概率/UV/天气码走 best_match，缺字段再互相回退。
MODEL_PRIMARY = "cma_grapes_global"
MODEL_FALLBACK = "best_match"
MODELS_PARAM = f"{MODEL_PRIMARY},{MODEL_FALLBACK}"

DAILY_FIELDS = (
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "uv_index_max",
    "weather_code",
)

# WMO 天气码 → 中文。没列到的区间一律「未知」，不要猜。
WMO_TEXT: dict[int, str] = {
    0: "晴",
    1: "多云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾",
}
WMO_RANGES: tuple[tuple[int, int, str], ...] = (
    (51, 57, "毛毛雨"),
    (61, 67, "雨"),
    (71, 77, "雪"),
    (80, 82, "阵雨"),
    (95, 99, "雷雨"),
)


def weather_text(code: int | None) -> str:
    if code is None:
        return "未知"
    if code in WMO_TEXT:
        return WMO_TEXT[code]
    for low, high, text in WMO_RANGES:
        if low <= code <= high:
            return text
    return "未知"


class UnknownCity(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class UpstreamError(Exception):
    """上游取数失败（超时、非 200、结构异常）。"""


@dataclass(frozen=True)
class WeatherSnapshot:
    city: str
    date: str
    t_min: float
    t_max: float
    feels_min: float
    feels_max: float
    precip_prob: float
    wind: float
    uv: float
    weather_code: int


@dataclass(frozen=True)
class WeatherResult:
    snapshot: WeatherSnapshot
    cached: bool
    stale: bool


# key = (lat, lon, date) -> (写入时间, 快照)
_cache: dict[tuple[float, float, str], tuple[float, WeatherSnapshot]] = {}


def clear_cache() -> None:
    _cache.clear()


def cache_key(city: City, date: str) -> tuple[float, float, str]:
    return (round(city.latitude, 3), round(city.longitude, 3), date)


def today_in(timezone: str) -> str:
    return datetime.now(ZoneInfo(timezone)).date().isoformat()


def _params(city: City) -> dict[str, str | float | int]:
    return {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "daily": ",".join(DAILY_FIELDS),
        "timezone": city.timezone,
        "forecast_days": 1,
        "models": MODELS_PARAM,
    }


def _series_value(daily: dict, base: str, model: str) -> float | None:
    series = daily.get(f"{base}_{model}")
    if not isinstance(series, list) or not series:
        return None
    head = series[0]
    if head is None:
        return None
    try:
        return float(head)
    except (TypeError, ValueError):
        return None


def _pick(daily: dict, base: str, preferred: str, fallback: str) -> float:
    """先取首选模型的字段，缺失/为 null 再退回另一个模型；都没有就报错。

    不静默填 0：0 是「测得是 0」，null 是「没这个数据」，两者不能混。
    """
    for model in (preferred, fallback):
        value = _series_value(daily, base, model)
        if value is not None:
            return value
    raise UpstreamError(f"天气服务缺少可用字段：{base}")


def _parse(city: City, date: str, payload: dict) -> WeatherSnapshot:
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise UpstreamError("天气服务返回结构异常")

    return WeatherSnapshot(
        city=city.name,
        date=date,
        # 温度/体感走 CMA
        t_min=_pick(daily, "temperature_2m_min", MODEL_PRIMARY, MODEL_FALLBACK),
        t_max=_pick(daily, "temperature_2m_max", MODEL_PRIMARY, MODEL_FALLBACK),
        feels_min=_pick(daily, "apparent_temperature_min", MODEL_PRIMARY, MODEL_FALLBACK),
        feels_max=_pick(daily, "apparent_temperature_max", MODEL_PRIMARY, MODEL_FALLBACK),
        wind=_pick(daily, "wind_speed_10m_max", MODEL_PRIMARY, MODEL_FALLBACK),
        # 降水概率 / UV / 天气码走 best_match
        precip_prob=_pick(
            daily, "precipitation_probability_max", MODEL_FALLBACK, MODEL_PRIMARY
        ),
        uv=_pick(daily, "uv_index_max", MODEL_FALLBACK, MODEL_PRIMARY),
        weather_code=int(_pick(daily, "weather_code", MODEL_FALLBACK, MODEL_PRIMARY)),
    )


async def _fetch_once(city: City) -> httpx.Response:
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        return await client.get(API_URL, params=_params(city))


async def fetch_daily(city: City, date: str) -> WeatherSnapshot:
    """打上游，超时类失败重试一次；HTTP 错误不重试。

    背景：api.open-meteo.com 在本机会间歇性 TLS 握手超时（TCP 能连、TLS 20s 超时），
    单次失败就 502 会让整页不可用，所以对超时做一次短重试。
    """
    response: httpx.Response | None = None
    for attempt in (1, 2):
        try:
            response = await _fetch_once(city)
            break
        except httpx.TimeoutException as exc:
            if attempt == 1:
                logger.warning("weather retry city=%s attempt=2", city.name)
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue
            raise UpstreamError(f"请求天气服务超时：{exc.__class__.__name__}") from exc
        except httpx.HTTPError as exc:
            # 连接被拒、DNS 失败这类不重试：换个时间也不会好，还多花一次请求
            raise UpstreamError(f"请求天气服务失败：{exc.__class__.__name__}") from exc

    assert response is not None
    if response.status_code != 200:
        # 4xx/5xx 不重试：重试也没用
        raise UpstreamError(f"天气服务返回 HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise UpstreamError("天气服务返回的不是 JSON") from exc

    return _parse(city, date, payload)


def _fresh(key: tuple[float, float, str], now: float) -> WeatherSnapshot | None:
    hit = _cache.get(key)
    if hit is None:
        return None
    stored_at, snapshot = hit
    if now - stored_at > CACHE_TTL_SECONDS:
        return None
    return snapshot


def _last_success(key: tuple[float, float, str]) -> WeatherSnapshot | None:
    """降级用：过期了也要能拿出来。"""
    hit = _cache.get(key)
    return hit[1] if hit else None


async def get_weather(city_name: str | None) -> WeatherResult:
    city = find_city(city_name)
    if city is None:
        raise UnknownCity(city_name or "")

    date = today_in(city.timezone)
    key = cache_key(city, date)

    started = time.perf_counter()
    fresh = _fresh(key, time.monotonic())
    if fresh is not None:
        logger.info(
            "weather city=%s date=%s cache=hit elapsed_ms=%.0f",
            city.name,
            date,
            (time.perf_counter() - started) * 1000,
        )
        return WeatherResult(fresh, cached=True, stale=False)

    try:
        snapshot = await fetch_daily(city, date)
    except UpstreamError:
        last = _last_success(key)
        elapsed = (time.perf_counter() - started) * 1000
        if last is not None:
            logger.warning(
                "weather city=%s date=%s cache=stale elapsed_ms=%.0f", city.name, date, elapsed
            )
            return WeatherResult(last, cached=True, stale=True)
        logger.error(
            "weather city=%s date=%s cache=miss elapsed_ms=%.0f upstream=failed",
            city.name,
            date,
            elapsed,
        )
        raise

    _cache[key] = (time.monotonic(), snapshot)
    logger.info(
        "weather city=%s date=%s cache=miss elapsed_ms=%.0f",
        city.name,
        date,
        (time.perf_counter() - started) * 1000,
    )
    return WeatherResult(snapshot, cached=False, stale=False)
