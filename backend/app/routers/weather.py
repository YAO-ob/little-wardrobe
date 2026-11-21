"""天气接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..data.cities import city_names
from ..schemas import WeatherOut
from ..weather import UnknownCity, UpstreamError, WeatherResult, get_weather, weather_text

router = APIRouter()


async def resolve_weather(city: str | None) -> WeatherResult:
    """取天气并把异常映射成 HTTP 语义；天气接口和推荐接口共用。"""
    try:
        return await get_weather(city)
    except UnknownCity as exc:
        options = "、".join(city_names())
        raise HTTPException(
            status_code=400,
            detail=f"不认识的城市：{exc.name or '(空)'}。可选：{options}",
        ) from exc
    except UpstreamError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "weather_upstream_failed", "message": str(exc)},
        ) from exc


def weather_out(result: WeatherResult) -> WeatherOut:
    snap = result.snapshot
    return WeatherOut(
        city=snap.city,
        date=snap.date,
        t_min=snap.t_min,
        t_max=snap.t_max,
        feels_min=snap.feels_min,
        feels_max=snap.feels_max,
        precip_prob=snap.precip_prob,
        wind=snap.wind,
        uv=snap.uv,
        weather_code=snap.weather_code,
        weather_text=weather_text(snap.weather_code),
        cached=result.cached,
        stale=result.stale,
    )


@router.get("", response_model=WeatherOut)
async def read_weather(
    city: str | None = Query(default=None, description="城市名，不传默认杭州"),
) -> WeatherOut:
    result = await resolve_weather(city)
    return weather_out(result)
