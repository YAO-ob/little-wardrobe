"""推荐接口：查库 + 规则 + 可选模型，带结果缓存与限流。

原则：任何限制都退化成规则结果，接口永远 200（天气上游失败除外，那是数据缺失）。
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import limits, llm_cache
from ..db import get_db
from ..llm import key_fingerprint, resolve_llm_config
from ..llm_pick import pick_with_llm
from ..models import Item, LlmMetric, utcnow
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

RATE_LIMIT_NOTICE = "请求太频繁，当前展示的是规则推荐"


def _record_metric(
    db: Session,
    *,
    source: str,
    cached: bool,
    attempts: int,
    fallback_reason: str | None,
    latency_ms: int,
    model: str | None,
    usage: dict[str, int | None] | None,
    is_byok: bool,
) -> None:
    """写指标失败绝不能影响响应；只记一条 warning。"""
    try:
        db.add(
            LlmMetric(
                created_at=utcnow(),
                mode="llm",
                source=source,
                cached=cached,
                attempts=attempts,
                fallback_reason=fallback_reason,
                latency_ms=latency_ms,
                model=model,
                tokens_prompt=(usage or {}).get("prompt_tokens"),
                tokens_completion=(usage or {}).get("completion_tokens"),
                is_byok=is_byok,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001 - 指标是旁路，不能拖垮主流程
        logger.warning("llm_metric write failed", exc_info=True)
        db.rollback()


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
    request: Request,
    response: Response,
    occasion: str | None = Query(default=None, description="casual / work / sport / formal"),
    city: str | None = Query(default=None, description="城市名，不传默认杭州"),
    mode: Literal["rules", "llm"] = Query(default="rules", description="rules 或 llm"),
    x_llm_key: str | None = Header(default=None, alias="X-LLM-Key"),
    db: Session = Depends(get_db),
) -> RecommendOut:
    started = time.perf_counter()
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
    by_id = {
        row.id: RuleItem(id=row.id, category=row.category, warmth=row.warmth, occasion=row.occasion)
        for row in rows
    }
    facts = WeatherFacts(
        date=snapshot.date,
        feels_min=snapshot.feels_min,
        feels_max=snapshot.feels_max,
    )

    plan = build_outfits(facts, list(by_id.values()), occasion)
    outfits = [_outfit_out(outfit.items, outfit.reason, thumbs) for outfit in plan.outfits]
    notice = plan.notice

    source = "rules"
    attempts = 0
    fallback_reason: str | None = None
    cached = False
    model_name: str | None = None
    usage: dict[str, int | None] | None = None
    is_byok = bool((x_llm_key or "").strip())

    if mode == "llm":
        client_key = limits.client_key(
            request.headers.get("X-Forwarded-For"),
            request.client.host if request.client else None,
        )
        config = resolve_llm_config(x_llm_key)
        if config is None:
            fallback_reason = "no_key"
            logger.info("llm_pick mode=llm source=rules attempts=0 fallback=no_key key=-")
            response.headers["X-RateLimit-Remaining"] = str(limits.remaining(client_key))
        else:
            model_name = config.model
            key = llm_cache.build_key(
                date=snapshot.date,
                occasion=occasion,
                weather_hash=llm_cache.hash_weather(snapshot),
                wardrobe_hash=llm_cache.hash_wardrobe(rows),
                mode=mode,
            )
            hit = llm_cache.get(key)

            if hit is not None and all(item_id in by_id for item_id in hit.item_ids):
                logger.info(
                    "llm_cache cache=hit occasion=%s key=%s", occasion or "-", key_fingerprint(key)
                )
                picked_items = [by_id[item_id] for item_id in hit.item_ids]
                source = "llm"
                attempts = hit.attempts
                cached = True
                outfits = [_outfit_out(picked_items, hit.reason, thumbs)] + outfits[1:]
                response.headers["X-RateLimit-Remaining"] = str(limits.remaining(client_key))
            else:
                logger.info("llm_cache cache=miss occasion=%s", occasion or "-")
                allowed, left = limits.try_consume(client_key)
                response.headers["X-RateLimit-Remaining"] = str(left)

                if not allowed:
                    fallback_reason = "rate_limited"
                    notice = f"{notice}；{RATE_LIMIT_NOTICE}" if notice else RATE_LIMIT_NOTICE
                    logger.warning("llm_rate_limited occasion=%s", occasion or "-")
                else:
                    picked = await pick_with_llm(config, facts, list(by_id.values()), occasion)
                    source = picked.source
                    attempts = picked.attempts
                    fallback_reason = picked.fallback_reason
                    usage = picked.usage
                    if picked.source == "llm" and picked.outfit:
                        outfits = [_outfit_out(picked.outfit, picked.reason, thumbs)] + outfits[1:]
                        llm_cache.put(
                            key,
                            llm_cache.CachedPick(
                                item_ids=tuple(item.id for item in picked.outfit),
                                reason=picked.reason,
                                attempts=picked.attempts,
                            ),
                        )
                    elif picked.fallback_reason:
                        # 降级结果不缓存：下次还要再试模型
                        logger.info("llm_cache skip=fallback reason=%s", picked.fallback_reason)

    if mode == "llm":
        _record_metric(
            db,
            source=source,
            cached=cached,
            # 命中缓存的那次没有真的调模型
            attempts=0 if cached else attempts,
            fallback_reason=fallback_reason,
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=model_name,
            usage=usage,
            is_byok=is_byok,
        )

    return RecommendOut(
        date=snapshot.date,
        weather=weather_out(weather),
        outfits=outfits,
        notice=notice,
        source=source,
        attempts=attempts,
        fallback_reason=fallback_reason,
        cached=cached,
    )
