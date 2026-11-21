"""搭配接口：把「今天穿这套」存进 outfits / outfit_items。"""

from __future__ import annotations

import json
from datetime import date as date_cls

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Item, Outfit, OutfitItem, utcnow
from ..rules import layer_from_category
from ..schemas import OutfitCreate, OutfitItemBrief, OutfitListOut, OutfitOut, primary_thumb

router = APIRouter()


@router.post("", response_model=OutfitOut, status_code=201)
def create_outfit(payload: OutfitCreate, db: Session = Depends(get_db)) -> OutfitOut:
    # 同一套重复提交不去重（「今天又穿了这套」是合法记录），但单件去重
    item_ids = list(dict.fromkeys(payload.item_ids))
    rows = (
        db.execute(
            select(Item).where(Item.id.in_(item_ids), Item.deleted_at.is_(None))
        )
        .scalars()
        .all()
    )
    found = {row.id for row in rows}
    missing = [item_id for item_id in item_ids if item_id not in found]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"以下单品不存在或已删除：{missing}",
        )

    worn_on = payload.weather.date if payload.weather else date_cls.today().isoformat()
    weather_json = (
        json.dumps(payload.weather.model_dump(), ensure_ascii=False)
        if payload.weather
        else None
    )

    outfit = Outfit(worn_on=worn_on, weather_json=weather_json, note=payload.note)
    db.add(outfit)
    db.flush()

    by_id = {row.id: row for row in rows}
    for item_id in item_ids:
        item_row = by_id[item_id]
        db.add(
            OutfitItem(
                outfit_id=outfit.id,
                item_id=item_id,
                # 存量优先，没填才按品类推导
                layer=item_row.layer or layer_from_category(item_row.category),
            )
        )
    db.commit()

    return OutfitOut(id=outfit.id, worn_on=outfit.worn_on, item_ids=item_ids)


@router.get("", response_model=OutfitListOut)
def list_outfits(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> OutfitListOut:
    total = (
        db.execute(
            select(func.count()).select_from(Outfit).where(Outfit.deleted_at.is_(None))
        ).scalar_one()
    )
    rows = (
        db.execute(
            select(Outfit)
            .options(selectinload(Outfit.items))
            .where(Outfit.deleted_at.is_(None))
            .order_by(Outfit.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    # 一次把涉及的 items 全查出来（含软删的），避免 N+1：limit=20 时总共 2 次查询
    item_ids = {link.item_id for row in rows for link in row.items}
    item_rows = (
        db.execute(
            select(Item).options(selectinload(Item.images)).where(Item.id.in_(item_ids))
        )
        .scalars()
        .all()
        if item_ids
        else []
    )
    by_id = {item.id: item for item in item_rows}

    def brief(link: OutfitItem) -> OutfitItemBrief:
        item = by_id.get(link.item_id)
        if item is None:
            return OutfitItemBrief(id=link.item_id)
        # 软删的单品保留 id 和品类，但不再给缩略图（历史记录不该消失）
        thumb = None if item.deleted_at else primary_thumb(item)
        return OutfitItemBrief(id=item.id, category=item.category, thumb_url=thumb)

    return OutfitListOut(
        total=total,
        outfits=[
            OutfitOut(
                id=row.id,
                worn_on=row.worn_on,
                item_ids=[link.item_id for link in sorted(row.items, key=lambda x: x.id)],
                items=[brief(link) for link in sorted(row.items, key=lambda x: x.id)[:6]],
            )
            for row in rows
        ],
    )


@router.delete("/{outfit_id}", status_code=204)
def delete_outfit(outfit_id: int, db: Session = Depends(get_db)) -> None:
    """软删：只打 deleted_at。outfit_items 不动，wear_log 视图会自动过滤掉。"""
    outfit = db.get(Outfit, outfit_id)
    if outfit is None or outfit.deleted_at:
        raise HTTPException(status_code=404, detail="搭配不存在")
    outfit.deleted_at = utcnow()
    db.commit()
