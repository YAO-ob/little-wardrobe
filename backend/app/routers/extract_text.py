"""纯文字录入识别：从一句话抽品类/厚薄/颜色/场合/材质。

与 classify 共用逐字段容错与置信度阈值（见 classify._normalize_fields），
失败一律 200 + source=none + reason，绝不让录入流程挂掉——与 classify 一致。
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Header

from ..llm import LLMError, chat_json, resolve_llm_config
from ..schemas import ExtractTextIn, ExtractTextOut
from .classify import _normalize_fields

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_TEXT = 300

SYSTEM_PROMPT = (
    "你是服装录入助手。用户会用一句话描述一件衣服，你从文本里抽取五个字段："
    "品类（category）、厚薄（warmth）、家族色（color_family）、适用场合（occasion）、材质（material）。\n"
    "只填文本里能确定的字段，不确定就给 null，不要猜，更不要编造。\n"
    "category 只能是：top（上装/衬衫/毛衣）、outer（外套）、bottom（下装/裤裙）、"
    "shoes（鞋）、accessory（配饰）、dress（连衣裙）。\n"
    "warmth 只能是 1（薄）、2（中）、3（厚），拿不准给 null。\n"
    "color_family 只能从这些里选：black/white/gray/beige/brown/blue/navy/green/red/pink/"
    "purple/yellow/orange/multi；拿不准给 null。\n"
    "occasion 是数组，元素只能从 casual（日常）、work（通勤/正式办公）、sport（运动）、"
    "formal（正式礼服）里选；标 0~3 个最贴切的，拿不准给空数组 []。\n"
    "material 是材质（如 亚麻/棉/羊毛/牛仔），文本没提就给 null。\n"
    "不要输出品牌和价格。\n"
    '只输出 JSON，形如 {"category":"top","warmth":1,"color_family":"beige",'
    '"occasion":["work"],"material":"亚麻","confidence":0.9}'
)


def _user_prompt(text: str) -> str:
    return f"请从下面这段描述里抽取字段，不确定的给 null：\n{text}"


def _material_from(data: dict, norm: dict) -> str | None:
    """置信度没过阈值（<0.6 或非法）时全部置 null，材质也不例外。"""
    if norm["reason"] in ("low_confidence", "invalid_confidence"):
        return None
    raw = data.get("material")
    if isinstance(raw, str):
        text = raw.strip()
        return text or None
    return None


async def extract_text_path(text: str, config) -> ExtractTextOut:  # noqa: ANN001
    """给脚本/路由复用：调模型 → 逐字段校验（含材质）。"""
    data, _usage = await chat_json(config, SYSTEM_PROMPT, _user_prompt(text))
    norm = _normalize_fields(data)
    return ExtractTextOut(**norm, material=_material_from(data, norm))


@router.post("/extract-text", response_model=ExtractTextOut)
async def extract_text(
    payload: ExtractTextIn,
    x_llm_key: str | None = Header(default=None, alias="X-LLM-Key"),
) -> ExtractTextOut:
    started = time.perf_counter()
    # 文本超长截断，不让它吞 token 或触发 422
    text = (payload.text or "")[:MAX_TEXT]

    config = resolve_llm_config(x_llm_key)
    if config is None:
        logger.info("extract_text source=none reason=no_key")
        return ExtractTextOut(source="none", reason="no_key")

    if not text.strip():
        return ExtractTextOut(source="none", reason="empty_text")

    try:
        result = await extract_text_path(text, config)
    except LLMError as exc:
        logger.warning(
            "extract_text source=none reason=%s elapsed_ms=%.0f",
            exc.reason,
            (time.perf_counter() - started) * 1000,
        )
        return ExtractTextOut(source="none", reason=exc.reason)

    logger.info(
        "extract_text source=%s reason=%s confidence=%s elapsed_ms=%.0f",
        result.source,
        result.reason or "none",
        result.confidence,
        (time.perf_counter() - started) * 1000,
    )
    return result
