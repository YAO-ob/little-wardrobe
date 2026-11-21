"""推荐接口：查库 + 调规则 + 可选让模型挑一套。规则在 app/rules.py，模型在 app/llm_pick.py。"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..llm import resolve_llm_config
from ..llm_pick import pick_with_llm
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
logger = logging.getLogger(__name__)


def _thumb(item: Item) -> str | None:
    if not item.images:
        return None
    primary = next((img for img in item.images if img.is_primary), item.images[0])
    return media_url(primary.thumb_path or primary.path)


def _outfit_out(
    items: tuple[RuleItem, ...] | list[RuleItem], reason: str, thumbs: dict[int, str | None]
) -> RecommendOutfitOut:
    return RecommendOutfitOut(
        items=[
            RecommendItemOut(
                id=item.id,
                category=item.category,
                warmth=item.warmth,
                layer=layer_of(item.category),
                thumb_url=thumbs.get(item.id),
            )
            for item in items
        ],
        reason=reason,
    )


@router.get("", response_model=RecommendOut)
async def recommend(
    occasion: str | None = Query(default=None, description="casual / work / sport / formal"),
    city: str | None = Query(default=None, description="城市名，不传默认杭州"),
    mode: Literal["rules", "llm"] = Query(default="rules", description="rules 或 llm"),
    x_llm_key: str | None = Header(default=None, alias="X-LLM-Key"),
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
    facts = WeatherFacts(
        date=snapshot.date,
        feels_min=snapshot.feels_min,
        feels_max=snapshot.feels_max,
    )

    plan = build_outfits(facts, rule_items, occasion)
    outfits = [_outfit_out(outfit.items, outfit.reason, thumbs) for outfit in plan.outfits]

    source = "rules"
    attempts = 0
    fallback_reason: str | None = None

    if mode == "llm":
        config = resolve_llm_config(x_llm_key)
        if config is None:
            fallback_reason = "no_key"
            logger.info("llm_pick mode=llm source=rules attempts=0 fallback=no_key key=-")
        else:
            picked = await pick_with_llm(config, facts, rule_items, occasion)
            source = picked.source
            attempts = picked.attempts
            fallback_reason = picked.fallback_reason
            if picked.source == "llm" and picked.outfit:
                # 只替换第一套，其余两套仍是规则结果
                outfits = [_outfit_out(picked.outfit, picked.reason, thumbs)] + outfits[1:]

    return RecommendOut(
        date=snapshot.date,
        weather=weather_out(weather),
        outfits=outfits,
        notice=plan.notice,
        source=source,
        attempts=attempts,
        fallback_reason=fallback_reason,
    )
