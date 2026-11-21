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


class WeatherOut(BaseModel):
    city: str
    date: str = Field(description="该城市时区的今天，YYYY-MM-DD")
    t_min: float = Field(description="当日最低气温，℃")
    t_max: float = Field(description="当日最高气温，℃")
    feels_min: float = Field(description="当日最低体感温度，℃")
    feels_max: float = Field(description="当日最高体感温度，℃")
    precip_prob: float = Field(description="当日最大降水概率，%")
    wind: float = Field(description="当日最大风速，km/h")
    uv: float = Field(description="当日最大 UV 指数，无量纲")
    weather_code: int = Field(description="WMO 天气码（取 best_match 模型，CMA 不提供）")
    weather_text: str = Field(description="天气码的中文描述，如「晴」「阵雨」；未知码返回「未知」")
    cached: bool = Field(
        description="true = 命中进程内缓存（按 城市坐标+日期 缓存 2 小时）"
    )
    stale: bool = Field(
        description=(
            "true = 上游失败，返回的是上一次的成功结果（可能是几小时前的）；"
            "前端应提示「天气可能不是最新」。cached 同时为 true"
        )
    )


class RecommendItemOut(BaseModel):
    id: int
    category: str
    warmth: int | None = None
    layer: str | None = Field(default=None, description="inner / mid / outer；下装鞋配饰为 null")
    thumb_url: str | None = Field(default=None, description="缩略图地址；没图就是 null")


class RecommendOutfitOut(BaseModel):
    items: list[RecommendItemOut]
    reason: str = Field(description="一句中文理由，说明为什么这么配")


class RecommendOut(BaseModel):
    date: str
    weather: WeatherOut
    outfits: list[RecommendOutfitOut] = Field(default_factory=list)
    notice: str | None = Field(
        default=None,
        description="衣橱缺品类等说明；例如「衣橱里没有下装，只能组出 1 套」",
    )
    source: str = Field(default="rules", description="第一套的来源：rules 或 llm")
    attempts: int = Field(default=0, description="调用模型的次数（0 表示没调）")
    fallback_reason: str | None = Field(
        default=None,
        description="降级原因：no_key / timeout / rate_limited / upstream_5xx / bad_json / invalid_ids …",
    )


class WeatherSnapshotIn(BaseModel):
    """前端回传的天气快照，只用于存进 outfits.weather_json。"""

    date: str
    t_min: float
    t_max: float
    feels_min: float
    feels_max: float
    precip_prob: float
    wind: float
    uv: float
    weather_code: int
    weather_text: str


class OutfitCreate(BaseModel):
    item_ids: list[int] = Field(min_length=1, description="这套包含的单品 id，不能为空")
    weather: WeatherSnapshotIn | None = Field(
        default=None, description="天气快照；不传则 worn_on 用今天"
    )
    note: str | None = None


class OutfitOut(BaseModel):
    id: int
    worn_on: str
    item_ids: list[int]


class OutfitListOut(BaseModel):
    total: int
    outfits: list[OutfitOut]


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
