"""从购物截图里提取商品信息（品牌/价格/材质/颜色/尺码）。

只做「建议」：不落库、不绑定单品。用户确认后走普通 PATCH 保存。
任何失败都返回 200 + reason，绝不 500。
"""

from __future__ import annotations

import base64
import io
import logging
import os
import time

from fastapi import APIRouter, Depends, File, Header, UploadFile
from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from ..llm import LLMError, chat_json_with_image, resolve_llm_config
from ..schemas import ReceiptOut

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_SIDE = 768
JPEG_QUALITY = 80
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
DEFAULT_MIN_CONFIDENCE = 0.6
TEXT_LIMIT = 32

SYSTEM_PROMPT = (
    "你是购物截图信息提取器。这是淘宝/京东等购物 App 的商品截图。\n"
    "只提取这几项：brand（品牌）、price（价格，数字）、material（材质）、"
    "color_family（颜色）、size（尺码）。\n"
    "看不清就给 null，**不要猜**。不要输出这五项以外的内容。\n"
    '只输出 JSON，形如 {"brand": "优衣库", "price": 199.0, "material": "棉",'
    ' "color_family": "藏青", "size": "M", "confidence": 0.88}'
)

USER_PROMPT = "提取这张截图里的商品信息，按 schema 输出 JSON。"


def min_confidence() -> float:
    raw = os.environ.get("EW_CLASSIFY_MIN_CONFIDENCE", "").strip()
    if not raw:
        return DEFAULT_MIN_CONFIDENCE
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_MIN_CONFIDENCE
    return value if 0.0 <= value <= 1.0 else DEFAULT_MIN_CONFIDENCE


def _encode(raw: bytes) -> tuple[str, str]:
    with PILImage.open(io.BytesIO(raw)) as img:
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        buffer = io.BytesIO()
        img.save(buffer, "JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buffer.getvalue()).decode("ascii"), "image/jpeg"


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed[:TEXT_LIMIT] if trimmed else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number >= 0 else None


def _empty(reason: str, confidence: float | None = None) -> ReceiptOut:
    return ReceiptOut(confidence=confidence, source="none", reason=reason)


def _validate(data: dict) -> ReceiptOut:
    raw_confidence = data.get("confidence")
    if (
        isinstance(raw_confidence, bool)
        or not isinstance(raw_confidence, (int, float))
        or not 0.0 <= float(raw_confidence) <= 1.0
    ):
        return _empty("invalid_confidence")

    confidence = float(raw_confidence)
    if confidence < min_confidence():
        return _empty("low_confidence", confidence)

    # price 不合法只丢 price，其它字段仍可用
    result = ReceiptOut(
        brand=_text(data.get("brand")),
        price=_number(data.get("price")),
        material=_text(data.get("material")),
        color_family=_text(data.get("color_family")),
        size=_text(data.get("size")),
        confidence=confidence,
        source="llm",
    )
    if all(
        value is None
        for value in (result.brand, result.price, result.material, result.color_family, result.size)
    ):
        return _empty("no_fields", confidence)
    return result


@router.post("/extract-receipt", response_model=ReceiptOut)
async def extract_receipt(
    file: UploadFile = File(...),
    x_llm_key: str | None = Header(default=None, alias="X-LLM-Key"),
) -> ReceiptOut:
    started = time.perf_counter()
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        return _empty("too_large")

    config = resolve_llm_config(x_llm_key)
    if config is None:
        logger.info("receipt source=none reason=no_key")
        return _empty("no_key")

    try:
        image_b64, mime = _encode(raw)
    except (UnidentifiedImageError, OSError):
        logger.warning("receipt source=none reason=bad_image")
        return _empty("bad_image")

    try:
        data, _usage = await chat_json_with_image(config, SYSTEM_PROMPT, USER_PROMPT, image_b64, mime)
    except LLMError as exc:
        logger.warning(
            "receipt source=none reason=%s elapsed_ms=%.0f",
            exc.reason,
            (time.perf_counter() - started) * 1000,
        )
        return _empty(exc.reason)

    result = _validate(data)
    logger.info(
        "receipt source=%s reason=%s confidence=%s elapsed_ms=%.0f",
        result.source,
        result.reason or "none",
        result.confidence,
        (time.perf_counter() - started) * 1000,
    )
    return result
