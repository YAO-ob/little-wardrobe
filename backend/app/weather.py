"""天气服务：Open-Meteo 日预报 + 进程内缓存 + 失败降级。

只做「取今天这一天」，不做多日预报、不做多时区换算。
缓存 key 用请求坐标（保留 3 位小数）+ 城市本地日期，**不用响应里的坐标**：
Open-Meteo 会把坐标吸附到网格（传 30.2741 可能返回 30.263618），
拿响应值当 key 会让缓存永远命中不了。
"""

from __future__ import annotations

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
CACHE_TTL_SECONDS = 2 * 60 * 60  # 2 小时，写死

DAILY_FIELDS = (
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "uv_index_max",
)


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
    }


def _parse(city: City, date: str, payload: dict) -> WeatherSnapshot:
    try:
        daily = payload["daily"]
        return WeatherSnapshot(
            city=city.name,
            date=date,
            t_min=float(daily["temperature_2m_min"][0]),
            t_max=float(daily["temperature_2m_max"][0]),
            feels_min=float(daily["apparent_temperature_min"][0]),
            feels_max=float(daily["apparent_temperature_max"][0]),
            precip_prob=float(daily["precipitation_probability_max"][0]),
            wind=float(daily["wind_speed_10m_max"][0]),
            uv=float(daily["uv_index_max"][0]),
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise UpstreamError("天气服务返回结构异常") from exc


async def fetch_daily(city: City, date: str) -> WeatherSnapshot:
    """打一次上游。任何失败都折成 UpstreamError，不把半截数据带出去。"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(API_URL, params=_params(city))
    except httpx.HTTPError as exc:
        raise UpstreamError(f"请求天气服务失败：{exc.__class__.__name__}") from exc

    if response.status_code != 200:
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
