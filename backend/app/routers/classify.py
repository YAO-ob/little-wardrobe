"""录入时的品类/厚薄预填：只做粗分类，失败一律 200 + reason，绝不让录入流程挂掉。

闭合校验与推荐链路同一思想：模型输出只在六个品类 / 三档厚薄里才有意义，
越界就当「没看清」，而不是硬塞一个标签。
"""

from __future__ import annotations

import base64
import io
import logging
import os
import time

from fastapi import APIRouter, Depends, Header, HTTPException
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..llm import LLMError, chat_json_with_image, resolve_llm_config
from ..models import Image
from ..schemas import COLOR_FAMILIES, OCCASIONS, ClassifyIn, ClassifyOut

logger = logging.getLogger(__name__)

router = APIRouter()

CATEGORIES = {"top", "outer", "bottom", "shoes", "accessory", "dress"}
WARMTHS = {1, 2, 3}
DEFAULT_MIN_CONFIDENCE = 0.6
CACHE_TTL_SECONDS = 30 * 60
MAX_SIDE = 512
JPEG_QUALITY = 80

# image_id -> (写入时的 monotonic, 结果)。只缓存成功结果，失败不缓存（补 key 后能重试）
_cache: dict[int, tuple[float, ClassifyOut]] = {}

SYSTEM_PROMPT = (
    "你是服装录入助手。看图判断四件事：品类（category）、厚薄（warmth）、家族色（color_family）、"
    "适用场合（occasion）。\n"
    "category 只能是：top（上装/衬衫/毛衣）、outer（外套）、bottom（下装/裤裙）、"
    "shoes（鞋）、accessory（配饰）、dress（连衣裙）。\n"
    "warmth 只能是 1（薄）、2（中）、3（厚），拿不准给 null。\n"
    "color_family 只能从这些里选：black/white/gray/beige/brown/blue/navy/green/red/pink/"
    "purple/yellow/orange/multi。只说家族色，不要猜精确色号、不要给 hex；"
    "有图案、多色或看不清就给 multi 或 null。\n"
    "occasion 是数组，元素只能从 casual（日常）、work（通勤/正式办公）、sport（运动）、"
    "formal（正式礼服）里选；一件衣服常适合多种场合，标 0~3 个最贴切的；"
    "看不准适用场合就给空数组 []，宁可少标不要乱标。\n"
    "不要判断材质和品牌。看不清就给低 confidence。\n"
    '只输出 JSON，形如 {"category": "shoes", "warmth": 2, "color_family": "black", "occasion": ["casual"], "confidence": 0.9}'
)

USER_PROMPT = "这张图里的单品是什么？按 schema 输出 JSON。"


def clear_cache() -> None:
    _cache.clear()


def min_confidence() -> float:
    raw = os.environ.get("EW_CLASSIFY_MIN_CONFIDENCE", "").strip()
    if not raw:
        return DEFAULT_MIN_CONFIDENCE
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_MIN_CONFIDENCE
    return value if 0.0 <= value <= 1.0 else DEFAULT_MIN_CONFIDENCE


def _result(
    *,
    category: str | None = None,
    warmth: int | None = None,
    color_family: str | None = None,
    occasion: list[str] | None = None,
    confidence: float | None = None,
    source: str = "none",
    reason: str | None = None,
) -> ClassifyOut:
    return ClassifyOut(
        category=category,
        warmth=warmth,
        color_family=color_family,
        occasion=occasion or [],
        confidence=confidence,
        source=source,
        reason=reason,
    )


def _encode(path) -> tuple[str, str]:  # noqa: ANN001
    """压到最长边 512 的 JPEG 再 base64：省 token，也不把原图发出去。"""
    with PILImage.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        buffer = io.BytesIO()
        img.save(buffer, "JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buffer.getvalue()).decode("ascii"), "image/jpeg"


def _normalize_fields(data: dict) -> dict:
    """逐字段容错 + 置信度阈值。classify 与 extract-text 共用这一套，避免两套逻辑漂移。

    返回归一化字段字典；置信度 < 阈值或非法时全部置 null（source=none）。
    """
    raw_confidence = data.get("confidence")

    if (
        isinstance(raw_confidence, bool)
        or not isinstance(raw_confidence, (int, float))
        or not 0.0 <= float(raw_confidence) <= 1.0
    ):
        return {
            "category": None,
            "warmth": None,
            "color_family": None,
            "occasion": [],
            "confidence": None,
            "source": "none",
            "reason": "invalid_confidence",
        }

    confidence = float(raw_confidence)
    if confidence < min_confidence():
        return {
            "category": None,
            "warmth": None,
            "color_family": None,
            "occasion": [],
            "confidence": confidence,
            "source": "none",
            "reason": "low_confidence",
        }

    # 逐字段容错：颜色判错不该连累品类，品类判错也不该连累颜色
    category = data.get("category")
    warmth = data.get("warmth")
    color = data.get("color_family")

    invalid = False
    if not isinstance(category, str) or category not in CATEGORIES:
        category = None
        invalid = True
    if warmth is not None and (isinstance(warmth, bool) or warmth not in WARMTHS):
        warmth = None
        invalid = True
    if color is not None and (not isinstance(color, str) or color not in COLOR_FAMILIES):
        color = None
        invalid = True

    # occasion 容错：必须是数组，越界元素丢弃（不连累其他字段）；空数组 = 看不清 / 任何场合可用
    raw_occasion = data.get("occasion")
    if isinstance(raw_occasion, list):
        occasion = [o for o in raw_occasion if isinstance(o, str) and o in OCCASIONS]
    else:
        occasion = []

    if category is None and warmth is None and color is None:
        return {
            "category": None,
            "warmth": None,
            "color_family": None,
            "occasion": occasion,
            "confidence": confidence,
            "source": "none",
            "reason": "invalid_label" if invalid else "no_fields",
        }

    return {
        "category": category,
        "warmth": warmth,
        "color_family": color,
        "occasion": occasion,
        "confidence": confidence,
        "source": "llm",
        "reason": "invalid_label" if invalid else None,
    }


def _validate(data: dict) -> ClassifyOut:
    return ClassifyOut(**_normalize_fields(data))


async def classify_path(path, config) -> ClassifyOut:  # noqa: ANN001
    """给脚本复用的入口：压图 → 调模型 → 逐字段校验。"""
    image_b64, mime = _encode(path)
    data, _usage = await chat_json_with_image(config, SYSTEM_PROMPT, USER_PROMPT, image_b64, mime)
    return _validate(data)


@router.post("", response_model=ClassifyOut)
async def classify(
    payload: ClassifyIn,
    x_llm_key: str | None = Header(default=None, alias="X-LLM-Key"),
    db: Session = Depends(get_db),
) -> ClassifyOut:
    started = time.perf_counter()
    image = db.get(Image, payload.image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="图片不存在")

    hit = _cache.get(payload.image_id)
    if hit is not None and time.monotonic() - hit[0] <= CACHE_TTL_SECONDS:
        logger.info(
            "classify image_id=%s source=cache reason=none elapsed_ms=%.0f",
            payload.image_id,
            (time.perf_counter() - started) * 1000,
        )
        return hit[1]

    config = resolve_llm_config(x_llm_key)
    if config is None:
        logger.info("classify image_id=%s source=none reason=no_key", payload.image_id)
        return _result(reason="no_key")

    settings = get_settings()
    try:
        result = await classify_path(settings.media_dir / image.path, config)
    except (FileNotFoundError, OSError):
        logger.warning("classify image_id=%s reason=image_missing", payload.image_id)
        return _result(reason="image_missing")
    except LLMError as exc:
        logger.warning(
            "classify image_id=%s source=none reason=%s elapsed_ms=%.0f",
            payload.image_id,
            exc.reason,
            (time.perf_counter() - started) * 1000,
        )
        return _result(reason=exc.reason)

    if result.source == "llm":
        _cache[payload.image_id] = (time.monotonic(), result)

    logger.info(
        "classify image_id=%s source=%s reason=%s confidence=%s elapsed_ms=%.0f",
        payload.image_id,
        result.source,
        result.reason or "none",
        result.confidence,
        (time.perf_counter() - started) * 1000,
    )
    return result
