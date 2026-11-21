"""天气接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..data.cities import city_names
from ..schemas import WeatherOut
from ..weather import UnknownCity, UpstreamError, get_weather

router = APIRouter()


@router.get("", response_model=WeatherOut)
async def read_weather(
    city: str | None = Query(default=None, description="城市名，不传默认杭州"),
) -> WeatherOut:
    try:
        result = await get_weather(city)
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
        cached=result.cached,
        stale=result.stale,
    )
