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
from ..schemas import ClassifyIn, ClassifyOut

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
    "你是服装录入助手。看图判断两件事：品类（category）和厚薄（warmth）。\n"
    "category 只能是：top（上装/衬衫/毛衣）、outer（外套）、bottom（下装/裤裙）、"
    "shoes（鞋）、accessory（配饰）、dress（连衣裙）。\n"
    "warmth 只能是 1（薄）、2（中）、3（厚），拿不准给 null。\n"
    "不要判断颜色、材质、品牌。看不清就给低 confidence。\n"
    '只输出 JSON，形如 {"category": "shoes", "warmth": 2, "confidence": 0.9}'
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
    confidence: float | None = None,
    source: str = "none",
    reason: str | None = None,
) -> ClassifyOut:
    return ClassifyOut(
        category=category, warmth=warmth, confidence=confidence, source=source, reason=reason
    )


def _encode(path) -> tuple[str, str]:  # noqa: ANN001
    """压到最长边 512 的 JPEG 再 base64：省 token，也不把原图发出去。"""
    with PILImage.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        buffer = io.BytesIO()
        img.save(buffer, "JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buffer.getvalue()).decode("ascii"), "image/jpeg"


def _validate(data: dict) -> ClassifyOut:
    category = data.get("category")
    warmth = data.get("warmth")
    raw_confidence = data.get("confidence")

    if (
        isinstance(raw_confidence, bool)
        or not isinstance(raw_confidence, (int, float))
        or not 0.0 <= float(raw_confidence) <= 1.0
    ):
        return _result(reason="invalid_confidence")

    confidence = float(raw_confidence)

    if not isinstance(category, str) or category not in CATEGORIES:
        return _result(confidence=confidence, reason="invalid_label")
    if warmth is not None and (isinstance(warmth, bool) or warmth not in WARMTHS):
        return _result(confidence=confidence, reason="invalid_label")

    if confidence < min_confidence():
        return _result(confidence=confidence, reason="low_confidence")

    return _result(category=category, warmth=warmth, confidence=confidence, source="llm")


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
        image_b64, mime = _encode(settings.media_dir / image.path)
    except (FileNotFoundError, OSError):
        logger.warning("classify image_id=%s reason=image_missing", payload.image_id)
        return _result(reason="image_missing")

    try:
        data, _usage = await chat_json_with_image(config, SYSTEM_PROMPT, USER_PROMPT, image_b64, mime)
    except LLMError as exc:
        logger.warning(
            "classify image_id=%s source=none reason=%s elapsed_ms=%.0f",
            payload.image_id,
            exc.reason,
            (time.perf_counter() - started) * 1000,
        )
        return _result(reason=exc.reason)

    result = _validate(data)
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
