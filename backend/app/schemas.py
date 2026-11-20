"""请求/响应模型。"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["top", "outer", "bottom", "shoes", "accessory", "dress"]
Occasion = Literal["casual", "work", "sport", "formal"]
Layer = Literal["inner", "mid", "outer"]

MEDIA_URL = "/media"


def media_url(path: str | None) -> str:
    return f"{MEDIA_URL}/{path}" if path else ""


class ImageOut(BaseModel):
    id: int
    url: str
    thumb_url: str
    width: int | None = None
    height: int | None = None


class ItemCreate(BaseModel):
    name: str = ""
    category: Category
    subcategory: str | None = None
    color_family: str | None = None
    color_hex: str | None = None
    season: list[str] = Field(default_factory=list)
    occasion: Occasion | None = None
    warmth: int | None = Field(default=None, ge=1, le=3)
    formality: int | None = Field(default=None, ge=1, le=5)
    layer: Layer | None = None
    material: str | None = None
    brand: str | None = None
    price: float | None = Field(default=None, ge=0)
    purchased_at: str | None = None
    note: str | None = None
    # 先传图后建单品：这里给已上传图片的 id
    image_ids: list[int] = Field(default_factory=list)


class ItemUpdate(BaseModel):
    name: str | None = None
    category: Category | None = None
    subcategory: str | None = None
    color_family: str | None = None
    color_hex: str | None = None
    season: list[str] | None = None
    occasion: Occasion | None = None
    warmth: int | None = Field(default=None, ge=1, le=3)
    formality: int | None = Field(default=None, ge=1, le=5)
    layer: Layer | None = None
    material: str | None = None
    brand: str | None = None
    price: float | None = Field(default=None, ge=0)
    purchased_at: str | None = None
    note: str | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    subcategory: str | None = None
    color_family: str | None = None
    color_hex: str | None = None
    season: list[str] = Field(default_factory=list)
    occasion: str | None = None
    warmth: int | None = None
    formality: int | None = None
    layer: str | None = None
    material: str | None = None
    brand: str | None = None
    price: float | None = None
    purchased_at: str | None = None
    note: str | None = None
    created_at: str | None = None
    images: list[ImageOut] = Field(default_factory=list)
    image: ImageOut | None = None  # 主图，方便卡片直接用


class ItemListOut(BaseModel):
    total: int
    items: list[ItemOut]


def parse_season(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def image_to_out(image) -> ImageOut:  # noqa: ANN001
    return ImageOut(
        id=image.id,
        url=media_url(image.path),
        thumb_url=media_url(image.thumb_path or image.path),
        width=image.width,
        height=image.height,
    )


def item_to_out(item) -> ItemOut:  # noqa: ANN001
    images = [image_to_out(img) for img in item.images]
    primary = None
    for img_model in item.images:
        if img_model.is_primary:
            primary = image_to_out(img_model)
            break
    if primary is None and images:
        primary = images[0]
    return ItemOut(
        id=item.id,
        name=item.name,
        category=item.category,
        subcategory=item.subcategory,
        color_family=item.color_family,
        color_hex=item.color_hex,
        season=parse_season(item.season),
        occasion=item.occasion,
        warmth=item.warmth,
        formality=item.formality,
        layer=item.layer,
        material=item.material,
        brand=item.brand,
        price=item.price,
        purchased_at=item.purchased_at,
        note=item.note,
        created_at=item.created_at,
        images=images,
        image=primary,
    )
