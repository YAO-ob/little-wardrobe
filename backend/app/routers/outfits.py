"""搭配接口：把「今天穿这套」存进 outfits / outfit_items。"""

from __future__ import annotations

import json
from datetime import date as date_cls

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Item, Outfit, OutfitItem, utcnow
from ..rules import layer_of
from ..schemas import OutfitCreate, OutfitListOut, OutfitOut

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
        db.add(
            OutfitItem(
                outfit_id=outfit.id,
                item_id=item_id,
                layer=layer_of(by_id[item_id].category),
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

    return OutfitListOut(
        total=total,
        outfits=[
            OutfitOut(
                id=row.id,
                worn_on=row.worn_on,
                item_ids=[link.item_id for link in sorted(row.items, key=lambda x: x.id)],
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
