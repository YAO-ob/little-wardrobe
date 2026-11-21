"""推荐接口：查库 + 调规则 + 拼响应。规则本身在 app/rules.py。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Item
from ..rules import RuleItem, WeatherFacts, build_outfits, layer_of
from ..schemas import (
    RecommendItemOut,
    RecommendOut,
    RecommendOutfitOut,
    media_url,
)
from .weather import resolve_weather, weather_out

router = APIRouter()


def _thumb(item: Item) -> str | None:
    if not item.images:
        return None
    primary = next((img for img in item.images if img.is_primary), item.images[0])
    return media_url(primary.thumb_path or primary.path)


@router.get("", response_model=RecommendOut)
async def recommend(
    occasion: str | None = Query(default=None, description="casual / work / sport / formal"),
    city: str | None = Query(default=None, description="城市名，不传默认杭州"),
    db: Session = Depends(get_db),
) -> RecommendOut:
    weather = await resolve_weather(city)
    snapshot = weather.snapshot

    rows = (
        db.execute(
            select(Item)
            .options(selectinload(Item.images))
            .where(Item.deleted_at.is_(None))
            .order_by(Item.id)
        )
        .scalars()
        .all()
    )

    thumbs = {row.id: _thumb(row) for row in rows}
    rule_items = [
        RuleItem(id=row.id, category=row.category, warmth=row.warmth, occasion=row.occasion)
        for row in rows
    ]

    plan = build_outfits(
        WeatherFacts(
            date=snapshot.date,
            feels_min=snapshot.feels_min,
            feels_max=snapshot.feels_max,
        ),
        rule_items,
        occasion,
    )

    return RecommendOut(
        date=snapshot.date,
        weather=weather_out(weather),
        outfits=[
            RecommendOutfitOut(
                items=[
                    RecommendItemOut(
                        id=item.id,
                        category=item.category,
                        warmth=item.warmth,
                        layer=layer_of(item.category),
                        thumb_url=thumbs.get(item.id),
                    )
                    for item in outfit.items
                ],
                reason=outfit.reason,
            )
            for outfit in plan.outfits
        ],
        notice=plan.notice,
    )
