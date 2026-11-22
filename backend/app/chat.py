"""对话入口：规则优先的意图解析 + 显式工具链。

设计取舍：意图解析不调模型也能跑（中文口语关键词覆盖率够高），只有
「规则没解析出场合」且用户带了 key 时才用模型兜底，且模型结果同样要过闭合校验。
工具链是显式的注册表，每一步都真的执行并把摘要记进 trace，方便前端展示和排查。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import recommend_service
from .db import get_db
from .llm import LLMError, chat_json, resolve_llm_config
from .llm_pick import validate_selection
from .models import Item
from .recommend_service import build_recommendation
from .routers.weather import resolve_weather
from .rules import RuleItem, WeatherFacts, build_outfits, filter_usable, layer_of
from .schemas import ChatIn, ChatOut, ChatTraceStep, RecommendOutfitOut
from .weather import WeatherResult, weather_text

logger = logging.getLogger(__name__)

router = APIRouter()

INTENTS = {"recommend", "reroll", "weather"}
OCCASIONS = {"casual", "work", "sport", "formal"}

WEATHER_WORDS = (
    "天气",
    "多少度",
    "几度",
    "冷不冷",
    "热不热",
    "下雨",
    "带伞",
    "温度",
    "冷不",
    "热不",
)
REROLL_WORDS = ("换", "再来", "别的", "另一套", "这套不行", "不喜欢", "其他")
OCCASION_WORDS: dict[str, tuple[str, ...]] = {
    "casual": ("约会", "电影", "吃饭", "逛街", "出去玩", "见朋友"),
    "work": ("上班", "开会", "通勤", "见客户", "工作", "加班"),
    "sport": ("跑步", "健身", "运动", "打球", "训练", "练车"),
    "formal": ("面试", "婚礼", "年会", "正式", "典礼", "答辩"),
}

OCCASION_LABEL = {"casual": "日常", "work": "通勤", "sport": "运动", "formal": "正式"}

INTENT_PROMPT = (
    "把用户关于穿衣服的话解析成 JSON。intent 只能是 recommend（想要搭配）、"
    "reroll（想换一套）、weather（只问天气）；occasion 只能是 casual/work/sport/formal 或 null；"
    'note 是原文里的关键场景词。只输出 JSON，形如 '
    '{"intent": "recommend", "occasion": "casual", "note": "约会"}'
)


@dataclass
class ParsedIntent:
    intent: str = "recommend"
    occasion: str | None = None
    note: str = ""


def parse_intent_rules(message: str) -> ParsedIntent:
    """关键词先跑：覆盖大多数中文口语句式。"""
    text = message.strip()

    occasion: str | None = None
    note = ""
    for value, words in OCCASION_WORDS.items():
        hit = next((word for word in words if word in text), None)
        if hit:
            occasion = value
            note = hit
            break

    if any(word in text for word in WEATHER_WORDS):
        return ParsedIntent(intent="weather", occasion=occasion, note=note)
    if any(word in text for word in REROLL_WORDS):
        return ParsedIntent(intent="reroll", occasion=occasion, note=note)
    return ParsedIntent(intent="recommend", occasion=occasion, note=note)


async def refine_with_llm(parsed: ParsedIntent, message: str, config) -> ParsedIntent:  # noqa: ANN001
    """规则没解析出场合时才问模型；任何异常/越界都保留规则结果。"""
    try:
        data, _usage = await chat_json(config, INTENT_PROMPT, message)
    except LLMError:
        return parsed

    intent = data.get("intent")
    occasion = data.get("occasion")
    note = data.get("note")

    if intent not in INTENTS:
        return parsed
    if occasion is not None and occasion not in OCCASIONS:
        return parsed

    return ParsedIntent(
        intent=intent,
        occasion=occasion if occasion is not None else parsed.occasion,
        note=note if isinstance(note, str) and note.strip() else parsed.note,
    )


@dataclass
class ToolContext:
    db: Session
    city: str | None
    occasion: str | None
    exclude_ids: list[int] = field(default_factory=list)
    weather: WeatherResult | None = None
    rows: list[Item] = field(default_factory=list)
    rule_items: list[RuleItem] = field(default_factory=list)
    plan: object | None = None


ToolResult = tuple[str, object]
Tool = Callable[[ToolContext], Awaitable[ToolResult]]


async def tool_get_weather(ctx: ToolContext) -> ToolResult:
    ctx.weather = await resolve_weather(ctx.city)
    snap = ctx.weather.snapshot
    summary = (
        f"{snap.city} {weather_text(snap.weather_code)} "
        f"{snap.t_min:.1f}–{snap.t_max:.1f}℃"
    )
    return summary, snap


async def tool_search_wardrobe(ctx: ToolContext) -> ToolResult:
    ctx.rows = recommend_service.load_wardrobe(ctx.db, ctx.exclude_ids)
    ctx.rule_items = list(recommend_service.to_rule_items(ctx.rows).values())
    usable = filter_usable(ctx.rule_items, ctx.occasion)
    return f"{len(usable)} 件可用单品", usable


async def tool_build_outfits(ctx: ToolContext) -> ToolResult:
    if ctx.weather is None:
        raise HTTPException(status_code=502, detail="缺天气，无法组套")
    snap = ctx.weather.snapshot
    facts = WeatherFacts(
        date=snap.date, feels_min=snap.feels_min, feels_max=snap.feels_max
    )
    ctx.plan = build_outfits(facts, ctx.rule_items, ctx.occasion)
    return f"{len(ctx.plan.outfits)} 套候选", ctx.plan


async def tool_validate(ctx: ToolContext) -> ToolResult:
    plan = ctx.plan
    if plan is None or not getattr(plan, "outfits", None):
        return "没有可校验的整套", None

    outfit = plan.outfits[0]
    pool = filter_usable(ctx.rule_items, ctx.occasion)
    payload = {"item_ids": [item.id for item in outfit.items]}
    picked, problems = validate_selection(payload, pool, want_outer=False)
    if picked is None:
        return f"校验未通过（{len(problems)} 处）", problems
    return f"校验通过 {len(picked)} 件", picked


TOOLS: dict[str, Tool] = {
    "get_weather": tool_get_weather,
    "search_wardrobe": tool_search_wardrobe,
    "build_outfits": tool_build_outfits,
    "validate": tool_validate,
}

CHAINS: dict[str, tuple[str, ...]] = {
    "recommend": ("get_weather", "search_wardrobe", "build_outfits", "validate"),
    "reroll": ("get_weather", "search_wardrobe", "build_outfits", "validate"),
    "weather": ("get_weather",),
}


def _reply(intent: str, occasion: str | None, note: str, ctx: ToolContext) -> str:
    if intent == "weather" and ctx.weather is not None:
        snap = ctx.weather.snapshot
        return (
            f"{snap.city}今天{weather_text(snap.weather_code)}，"
            f"{snap.t_min:.1f}–{snap.t_max:.1f}℃，"
            f"体感 {snap.feels_min:.1f}–{snap.feels_max:.1f}℃"
        )

    scene = note or (OCCASION_LABEL[occasion] if occasion else "")
    if intent == "reroll":
        return f"换一套，还是{scene}" if scene else "换一套，再看看"
    if occasion:
        return f"正在衣柜里为你挑适合{scene}的搭配"
    return "正在衣柜里为你挑今天能穿的搭配"


@router.post("", response_model=ChatOut)
async def chat(
    payload: ChatIn,
    x_llm_key: str | None = Header(default=None, alias="X-LLM-Key"),
    db: Session = Depends(get_db),
) -> ChatOut:
    message = (payload.message or "").strip()
    if not message or len(message) > 200:
        raise HTTPException(status_code=422, detail="消息不能为空且不超过 200 字")

    parsed = parse_intent_rules(message)
    config = resolve_llm_config(x_llm_key)
    if parsed.occasion is None and config is not None:
        parsed = await refine_with_llm(parsed, message, config)

    ctx = ToolContext(
        db=db,
        city=payload.city,
        occasion=payload.occasion or parsed.occasion,
        exclude_ids=list(payload.exclude_ids or []),
    )

    trace: list[ChatTraceStep] = []
    for name in CHAINS[parsed.intent]:
        started = time.perf_counter()
        summary, _payload = await TOOLS[name](ctx)
        trace.append(
            ChatTraceStep(
                tool=name, summary=summary, ms=int((time.perf_counter() - started) * 1000)
            )
        )

    if parsed.intent == "weather":
        return ChatOut(
            reply=_reply("weather", ctx.occasion, parsed.note, ctx),
            intent="weather",
            occasion=ctx.occasion,
            trace=trace,
            outfits=[],
            source="rules",
            fallback_reason=None,
        )

    # 真正的推荐结果仍由 recommend_service 统一产出（模型、缓存、限流、指标都在那儿）
    result, _remaining = await build_recommendation(
        db,
        city=payload.city,
        occasion=ctx.occasion,
        mode=payload.mode,
        llm_key=x_llm_key,
        exclude_ids=list(payload.exclude_ids or []),
    )

    outfits: list[RecommendOutfitOut] = result.outfits
    return ChatOut(
        reply=_reply(parsed.intent, ctx.occasion, parsed.note, ctx),
        intent=parsed.intent,
        occasion=ctx.occasion,
        trace=trace,
        outfits=outfits,
        source=result.source,
        fallback_reason=result.fallback_reason,
    )
