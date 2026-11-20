"""单品接口。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import get_db
from ..imaging import DERIVED_WIDTH
from ..models import Image, Item, utcnow
from ..schemas import ItemCreate, ItemListOut, ItemOut, ItemUpdate, item_to_out

router = APIRouter()

CATEGORY_LABELS = {
    "top": "上衣",
    "outer": "外套",
    "bottom": "下装",
    "shoes": "鞋",
    "accessory": "配饰",
    "dress": "连衣裙",
}


def _load(db: Session, item_id: int) -> Item:
    stmt = select(Item).options(selectinload(Item.images)).where(Item.id == item_id)
    item = db.execute(stmt).scalar_one_or_none()
    if item is None or item.deleted_at:
        raise HTTPException(status_code=404, detail="单品不存在")
    return item


def _staged_stem(image: Image) -> str | None:
    """从 tmp 里的展示图文件名反推 stem；不是暂存图就返回 None。"""
    name = Path(image.path).name
    suffix = f"_{DERIVED_WIDTH}.webp"
    if not name.endswith(suffix):
        return None
    return name[: -len(suffix)]


def _staged_files(image: Image) -> list[str]:
    """这张图在 tmp 里应有的相对路径（派生图两档）。"""
    if not image.path.startswith("tmp/"):
        return []
    return [v for v in (image.path, image.thumb_path) if v and v.startswith("tmp/")]


def _assert_staged_files(image: Image) -> None:
    """搬之前先确认文件都在：缺了就直接报 500，别静默跳过留下指向 tmp 的路径。"""
    settings = get_settings()
    missing = [rel for rel in _staged_files(image) if not (settings.media_dir / rel).exists()]
    if missing:
        raise HTTPException(status_code=500, detail="暂存文件丢失，请重新上传")


def _promote(image: Image) -> None:
    """把 media/tmp 下的原图与两档派生图搬进正式目录，并改写 path。"""
    if not image.path.startswith("tmp/"):
        return  # 老数据：已经躺在正式目录里了

    settings = get_settings()
    stem = _staged_stem(image)
    if stem is None:
        return

    tmp_dir = settings.tmp_dir
    # 原图扩展名不定，按 stem 找；排除同 stem 的派生图
    for src in tmp_dir.glob(f"{stem}.*"):
        if src.is_file() and not src.name.startswith(f"{stem}_"):
            os.replace(src, settings.originals_dir / src.name)

    for attr in ("path", "thumb_path"):
        value: str | None = getattr(image, attr)
        if not value or not value.startswith("tmp/"):
            continue
        src = settings.media_dir / value
        if not src.exists():
            # 正常情况下 _assert_staged_files 已经拦住了，这里是兜底
            raise HTTPException(status_code=500, detail="暂存文件丢失，请重新上传")
        os.replace(src, settings.derived_dir / src.name)
        setattr(image, attr, f"derived/{src.name}")


def _attach_images(db: Session, item: Item, image_ids: list[int]) -> None:
    if not image_ids:
        return
    images = (
        db.execute(
            select(Image)
            .where(Image.id.in_(image_ids), Image.item_id.is_(None))
            .order_by(Image.id)
        )
        .scalars()
        .all()
    )
    missing = set(image_ids) - {img.id for img in images}
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"以下图片不存在或已被占用：{sorted(missing)}",
        )
    # 先全部校验再搬，避免搬到一半失败留下半套文件
    for image in images:
        _assert_staged_files(image)
    for index, image in enumerate(images):
        _promote(image)
        image.item_id = item.id
        image.is_primary = index == 0


@router.post("", response_model=ItemOut, status_code=201)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)) -> ItemOut:
    item = Item(
        name=payload.name.strip() or CATEGORY_LABELS.get(payload.category, "单品"),
        category=payload.category,
        subcategory=payload.subcategory,
        color_family=payload.color_family,
        color_hex=payload.color_hex,
        season=json.dumps(payload.season, ensure_ascii=False) if payload.season else None,
        occasion=payload.occasion,
        warmth=payload.warmth,
        formality=payload.formality,
        layer=payload.layer,
        material=payload.material,
        brand=payload.brand,
        price=payload.price,
        purchased_at=payload.purchased_at,
        note=payload.note,
    )
    db.add(item)
    db.flush()
    try:
        _attach_images(db, item, payload.image_ids)
    except Exception:
        # 挂图失败（暂存文件丢失 / id 非法）：整条回滚，不留下半个单品
        db.rollback()
        raise
    db.commit()
    return item_to_out(_load(db, item.id))


@router.get("", response_model=ItemListOut)
def list_items(
    category: list[str] | None = Query(default=None),
    occasion: str | None = None,
    q: str | None = None,
    incomplete: bool = False,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ItemListOut:
    conditions = [Item.deleted_at.is_(None)]
    if category:
        conditions.append(Item.category.in_(category))
    if occasion:
        conditions.append(Item.occasion == occasion)
    if q:
        conditions.append(Item.name.contains(q))
    if incomplete:
        conditions.append(or_(Item.color_family.is_(None), Item.color_family == ""))

    total = db.execute(select(func.count()).select_from(Item).where(*conditions)).scalar_one()
    stmt = (
        select(Item)
        .options(selectinload(Item.images))
        .where(*conditions)
        .order_by(Item.created_at.desc(), Item.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = db.execute(stmt).scalars().all()
    return ItemListOut(total=total, items=[item_to_out(item) for item in items])


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)) -> ItemOut:
    return item_to_out(_load(db, item_id))


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(item_id: int, payload: ItemUpdate, db: Session = Depends(get_db)) -> ItemOut:
    item = _load(db, item_id)
    data = payload.model_dump(exclude_unset=True)
    if "season" in data:
        season = data.pop("season") or []
        item.season = json.dumps(season, ensure_ascii=False) if season else None
    for field, value in data.items():
        setattr(item, field, value)
    item.updated_at = utcnow()
    db.commit()
    return item_to_out(_load(db, item_id))


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)) -> None:
    item = _load(db, item_id)
    item.deleted_at = utcnow()
    db.commit()
