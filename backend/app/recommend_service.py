"""推荐主流程：查天气 + 查单品 + 规则 + 可选模型，带缓存、限流与指标。

从 routers/recommend.py 抽出来，供 /api/recommend 和 /api/chat 共用；
行为保持不变：任何限制都退化成规则结果（天气上游失败仍然抛 502）。
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import limits, llm_cache
from .llm import key_fingerprint, resolve_llm_config
from .llm_pick import pick_with_llm
from .models import Item, LlmMetric, utcnow
from .rules import RuleItem, WeatherFacts, build_outfits, layer_of
from .schemas import (
    RecommendItemOut,
    RecommendOut,
    RecommendOutfitOut,
    primary_thumb,
)
from .routers.weather import resolve_weather, weather_out

logger = logging.getLogger(__name__)

RATE_LIMIT_NOTICE = "请求太频繁，当前展示的是规则推荐"


def record_metric(
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


def outfit_out(
    items: tuple[RuleItem, ...] | list[RuleItem], reason: str, thumbs: dict[int, str | None]
) -> RecommendOutfitOut:
    return RecommendOutfitOut(
        items=[
            RecommendItemOut(
                id=item.id,
                category=item.category,
                warmth=item.warmth,
                layer=layer_of(item),
                thumb_url=thumbs.get(item.id),
            )
            for item in items
        ],
        reason=reason,
    )


def load_wardrobe(db: Session, exclude_ids: list[int] | None = None) -> list[Item]:
    """未软删的单品，按 id 升序；exclude_ids 里的直接剔除。"""
    excluded = set(exclude_ids or [])
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
    return [row for row in rows if row.id not in excluded]


def to_rule_items(rows: list[Item]) -> dict[int, RuleItem]:
    return {
        row.id: RuleItem(
            id=row.id,
            category=row.category,
            warmth=row.warmth,
            occasion=row.occasion,
            formality=row.formality,
            layer=row.layer,
        )
        for row in rows
    }


async def build_recommendation(
    db: Session,
    *,
    city: str | None,
    occasion: str | None,
    mode: str,
    llm_key: str | None,
    exclude_ids: list[int] | None = None,
    client_key: str = "",
) -> tuple[RecommendOut, int | None]:
    """返回 (推荐结果, 剩余限流额度)。额度为 None 时调用方不设响应头。"""
    started = time.perf_counter()
    weather = await resolve_weather(city)
    snapshot = weather.snapshot

    rows = load_wardrobe(db, exclude_ids)
    thumbs = {row.id: primary_thumb(row) for row in rows}
    by_id = to_rule_items(rows)

    facts = WeatherFacts(
        date=snapshot.date,
        feels_min=snapshot.feels_min,
        feels_max=snapshot.feels_max,
    )

    plan = build_outfits(facts, list(by_id.values()), occasion)
    outfits = [outfit_out(outfit.items, outfit.reason, thumbs) for outfit in plan.outfits]
    notice = plan.notice

    source = "rules"
    attempts = 0
    fallback_reason: str | None = None
    cached = False
    model_name: str | None = None
    usage: dict[str, int | None] | None = None
    is_byok = bool((llm_key or "").strip())
    remaining: int | None = None

    if mode == "llm":
        config = resolve_llm_config(llm_key)
        if config is None:
            fallback_reason = "no_key"
            logger.info("llm_pick mode=llm source=rules attempts=0 fallback=no_key key=-")
            remaining = limits.remaining(client_key)
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
                outfits = [outfit_out(picked_items, hit.reason, thumbs)] + outfits[1:]
                remaining = limits.remaining(client_key)
            else:
                logger.info("llm_cache cache=miss occasion=%s", occasion or "-")
                allowed, left = limits.try_consume(client_key)
                remaining = left

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
                        outfits = [outfit_out(picked.outfit, picked.reason, thumbs)] + outfits[1:]
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
        record_metric(
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

    return (
        RecommendOut(
            date=snapshot.date,
            weather=weather_out(weather),
            outfits=outfits,
            notice=notice,
            source=source,
            attempts=attempts,
            fallback_reason=fallback_reason,
            cached=cached,
        ),
        remaining,
    )
