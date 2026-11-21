"""城市列表接口：前端下拉的唯一来源。"""

from __future__ import annotations

from fastapi import APIRouter

from ..data.cities import DEFAULT_CITY, city_names

router = APIRouter()


@router.get("")
def list_cities() -> dict[str, object]:
    return {"cities": city_names(), "default": DEFAULT_CITY}
