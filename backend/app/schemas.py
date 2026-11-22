"""请求/响应模型。"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["top", "outer", "bottom", "shoes", "accessory", "dress"]
Occasion = Literal["casual", "work", "sport", "formal"]
Layer = Literal["inner", "mid", "outer"]

# 洗护符号只允许这 12 个编码：自由文本会让「30度/30℃/温水」三种写法并存，
# 以后想按洗护方式筛选就没法做。
COLOR_FAMILIES = (
    "black",
    "white",
    "gray",
    "beige",
    "brown",
    "blue",
    "navy",
    "green",
    "red",
    "pink",
    "purple",
    "yellow",
    "orange",
    "multi",
)


CARE_SYMBOLS = (    "wash_30",
    "wash_40",
    "hand_wash",
    "no_wash",
    "bleach_ok",
    "no_bleach",
    "tumble_low",
    "no_tumble",
    "iron_low",
    "no_iron",
    "dry_clean",
    "no_dry_clean",
)


# 互斥组：同一组最多选一个，否则语义矛盾（都「可漂白」了还「不可漂白」）
CARE_EXCLUSIVE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("wash_30", "wash_40", "hand_wash", "no_wash"),
    ("bleach_ok", "no_bleach"),
    ("tumble_low", "no_tumble"),
    ("iron_low", "no_iron"),
    ("dry_clean", "no_dry_clean"),
)


def _validate_color_family(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    if text not in COLOR_FAMILIES:
        raise ValueError(
            f"颜色只能是这些之一：{'、'.join(COLOR_FAMILIES)}（中文只用于显示）"
        )
    return text


def _validate_care_symbols(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    unknown = [code for code in value if code not in CARE_SYMBOLS]
    if unknown:
        raise ValueError(f"不认识的洗护符号：{'、'.join(unknown)}")
    for group in CARE_EXCLUSIVE_GROUPS:
        chosen = [code for code in value if code in group]
        if len(chosen) > 1:
            raise ValueError(f"洗护符号互斥：{'、'.join(chosen)} 只能选一个")
    return value

MEDIA_URL = "/media"


def media_url(path: str | None) -> str:
    return f"{MEDIA_URL}/{path}" if path else ""


def primary_thumb(item) -> str | None:  # noqa: ANN001
    """单品主图缩略图；推荐与搭配历史共用这一处，避免两套实现漂移。"""
    if not item.images:
        return None
    primary = next((img for img in item.images if img.is_primary), item.images[0])
    return media_url(primary.thumb_path or primary.path)


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
    size: str | None = Field(default=None, max_length=16)
    purchase_url: str | None = Field(default=None, max_length=500)
    care_text: str | None = None
    care_symbols: list[str] = Field(default_factory=list)
    note: str | None = None
    # 先传图后建单品：这里给已上传图片的 id
    image_ids: list[int] = Field(default_factory=list)

    _care = field_validator("care_symbols")(_validate_care_symbols)
    _color = field_validator("color_family")(_validate_color_family)


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
    size: str | None = Field(default=None, max_length=16)
    purchase_url: str | None = Field(default=None, max_length=500)
    care_text: str | None = None
    care_symbols: list[str] | None = None
    note: str | None = None

    _care = field_validator("care_symbols")(_validate_care_symbols)
    _color = field_validator("color_family")(_validate_color_family)


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
    size: str | None = None
    purchase_url: str | None = None
    care_text: str | None = None
    care_symbols: list[str] = Field(default_factory=list)
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
    observed_at: str = Field(default="", description="这条数据对应的日期，YYYY-MM-DD")
    fetched_at: str = Field(
        default="", description="抓取时刻（ISO，含时区）；stale 时前端用它算「几小时前」"
    )
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
    cached: bool = Field(
        default=False,
        description="true = 命中推荐结果缓存（只缓存模型成功的结果，30 分钟）",
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


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=1000)


class ChatIn(BaseModel):
    message: str = Field(default="", max_length=200)
    city: str | None = None
    occasion: str | None = None
    exclude_ids: list[int] = Field(default_factory=list)
    mode: Literal["rules", "llm"] = "rules"
    history: list[ChatHistoryMessage] = Field(default_factory=list)


class ChatTraceStep(BaseModel):
    tool: str
    summary: str
    ms: int


class ChatOut(BaseModel):
    reply: str
    intent: str
    occasion: str | None = None
    trace: list[ChatTraceStep] = Field(default_factory=list)
    outfits: list["RecommendOutfitOut"] = Field(default_factory=list)
    source: str = "rules"
    fallback_reason: str | None = None


class ReceiptOut(BaseModel):
    brand: str | None = None
    price: float | None = None
    material: str | None = None
    color_family: str | None = None
    size: str | None = None
    confidence: float | None = None
    source: str = "none"
    reason: str | None = None


class ClassifyIn(BaseModel):
    image_id: int


class ClassifyOut(BaseModel):
    category: str | None = None
    warmth: int | None = None
    color_family: str | None = None
    confidence: float | None = None
    source: str = "none"
    reason: str | None = None


class OutfitItemBrief(BaseModel):
    id: int
    category: str | None = None
    thumb_url: str | None = None


class OutfitOut(BaseModel):
    id: int
    worn_on: str
    item_ids: list[int]
    # 历史记录用：最多 6 件的摘要；软删的单品仍给 id，thumb_url 为 null
    items: list[OutfitItemBrief] = Field(default_factory=list)


class OutfitListOut(BaseModel):
    total: int
    outfits: list[OutfitOut]


class TokensOut(BaseModel):
    prompt: int = 0
    completion: int = 0


class LatencyOut(BaseModel):
    avg: float | None = None
    p50: int | None = None
    p95: int | None = None


class MetricsOut(BaseModel):
    days: int
    total_calls: int = Field(description="窗口内 mode=llm 的请求数")
    llm_success: int = Field(description="真实模型调用成功（source=llm 且未命中缓存）")
    cache_hits: int = Field(description="命中推荐缓存的请求数")
    fallbacks: int = Field(description="退化成规则结果的请求数")
    fallback_by_reason: dict[str, int] = Field(default_factory=dict)
    by_model: dict[str, int] = Field(
        description="按模型统计的**模型调用次数**（只算 attempts>0；缓存命中/限流不计）"
    )
    tokens: TokensOut = Field(
        default_factory=TokensOut,
        description="只累加非空值：降级请求的 token 记 None，不会被当成 0",
    )
    latency_ms: LatencyOut = Field(
        default_factory=LatencyOut,
        description="请求级耗时（含缓存命中、限流、无 key 这些很快的请求）",
    )
    model_latency_ms: LatencyOut = Field(
        default_factory=LatencyOut,
        description="真实模型调用耗时（只算 attempts>0）。对外报延迟用这个",
    )
    byok_calls: int = Field(description="key 来自请求头 X-LLM-Key 的次数")
    server_key_calls: int = Field(description="key 来自环境变量（或无 key）的次数")


def parse_season(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def parse_care_symbols(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    # 库里就算混进了脏数据，出口也只放行编码表里的值
    return [code for code in (str(v) for v in value) if code in CARE_SYMBOLS]


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
        color_family=item.color_family if item.color_family in COLOR_FAMILIES else None,
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
        size=item.size,
        purchase_url=item.purchase_url,
        care_text=item.care_text,
        care_symbols=parse_care_symbols(item.care_symbols),
        note=item.note,
        created_at=item.created_at,
        images=images,
        image=primary,
    )
