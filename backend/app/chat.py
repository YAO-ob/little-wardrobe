"""对话入口：有 key 时一次调用同时产出「回复 + 意图 + 选品」，无 key 时退回模板。

底线不变：意图/场合越界就丢弃、选品必须过候选池四条硬校验、失败降级规则结果。
模型只能通过 item_ids 影响搭配，**不允许它用文字描述穿搭**——用户看不到具体是哪件。
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import recommend_service
from .db import get_db
from .llm import LLMConfig, LLMError, chat_json_messages, resolve_llm_config
from .llm_pick import build_pool, validate_selection
from .models import Item
from .routers.weather import resolve_weather
from .rules import (
    RuleItem,
    WeatherFacts,
    build_outfits,
    clean_note,
    filter_usable,
    need_outer,
    need_warmth,
)
from .schemas import ChatIn, ChatOut, ChatTraceStep, RecommendOutfitOut, primary_thumb
from .weather import WeatherResult, WeatherSnapshot, now_iso, today_in, weather_text

logger = logging.getLogger(__name__)

router = APIRouter()

INTENTS = {"recommend", "reroll", "weather", "chat"}
OCCASIONS = {"casual", "work", "sport", "formal"}

WEATHER_WORDS = (
    "天气",
    "多少度",
    "几度",
    "冷不冷",
    "热不热",
    "冷吗",
    "热吗",
    "下雨",
    "带伞",
    "温度",
    "冷不",
    "热不",
)
# 寒暄优先：说「你好」不该被当成问天气
GREETING_WORDS = (
    "你好",
    "您好",
    "hi",
    "hello",
    "在吗",
    "早上好",
    "早啊",
    "早安",
    "午安",
    "晚安",
    "早",
    "晚上好",
    "嗨",
    "哈喽",
    "哈啰",
    "谢谢",
    "谢了",
    "好的",
    "收到",
)
# 寒暄里夹了这些词就还是原来的意图（「你好，今天冷吗」确实在问天气）
INTENT_GUARD_WORDS = WEATHER_WORDS + ("度", "冷", "热", "伞", "穿什么", "穿啥", "搭配", "推荐")
# 穿着词：命中就强制 recommend，模型不能推翻（否则「上海今天穿什么」会飘成天气）
CLOTHING_WORDS = (
    "穿什么",
    "穿啥",
    "怎么穿",
    "搭配",
    "配一套",
    "穿哪件",
    "带什么衣服",
    "穿点什么",
)
REROLL_WORDS = ("换", "再来", "别的", "另一套", "这套不行", "不喜欢", "其他")
OCCASION_WORDS: dict[str, tuple[str, ...]] = {
    "casual": ("约会", "电影", "吃饭", "逛街", "出去玩", "见朋友"),
    "work": ("上班", "开会", "通勤", "见客户", "工作", "加班"),
    "sport": ("跑步", "健身", "运动", "打球", "训练", "练车"),
    "formal": ("面试", "婚礼", "年会", "正式", "典礼", "答辩"),
}

OCCASION_LABEL = {"casual": "日常", "work": "通勤", "sport": "运动", "formal": "正式"}

PERSONA = (
    "你是用户衣柜里的管家，说话简短、自然、有点幽默，不要客套话和感叹号堆砌。"
    "你熟悉用户衣橱里有什么，只在被问到穿着时才推荐，一两句话说完，不要列清单，不要用 emoji。"
    "不能编造衣橱里没有的衣服；不确定的事就说不确定。"
    "不要报具体温度数字（不要说「8 到 16 度」），日常寒暄用「有点凉」「挺暖和」「雾蒙蒙的」这类说法；"
    "只有用户明确问多少度 / 冷不冷 / 下不下雨时，才给数字。"
    "寒暄不必每句都带天气：一半的情况只回应问候本身（「在的，需要我看看穿什么吗？」「不客气，随时喊我」），"
    "不要每句都用同一个天气句式收尾。如果上一轮已经提过天气，这一轮不要再复述同一个天气描述。"
    "不要臆测用户的状态或情绪（不要说「累了」「辛苦了」「今天心情不错吧」这类），除非用户自己提到；"
    "不知道就只回应问候本身。"
    "推荐搭配时只能用给你的候选 id，绝不自己发明 id，也不要用文字描述具体搭配（用户看卡片）。"
    "候选里如果有备注与用户这句话语义相关的（谁送的、纪念日、某次旅行的纪念），"
    "优先选它，即使另一件参数更接近。"
    "只在用户的话明确指向备注信息时才提（谁送的、纪念日、某次旅行）；"
    "泛问（今天穿什么、随便配、有什么推荐）不要提备注，同一段对话里也不要反复提同一个备注。"
    "不许编造备注里没有的内容，备注没写的事就当不知道。"
    '只输出 JSON：{"reply": "一句话回应(<=60字)", "intent": "recommend|reroll|weather|chat", '
    '"occasion": "casual|work|sport|formal|null", "item_ids": [int]}'
)

# few-shot 用真实的 user/assistant 轮次，比塞在 system 里更稳
FEW_SHOT: list[tuple[str, str]] = [
    (
        "你好",
        '{"reply":"你好呀，今天雾蒙蒙的有点凉，出门记得加件外套。","intent":"chat",'
        '"occasion":null,"item_ids":[]}',
    ),
    (
        "我想穿休闲点去约会",
        '{"reply":"那就挑套松快的，约会别穿太板正。","intent":"recommend",'
        '"occasion":"casual","item_ids":[3,8,12,15]}',
    ),
    (
        "在吗",
        '{"reply":"在的，需要我看看穿什么吗？","intent":"chat",'
        '"occasion":null,"item_ids":[]}',
    ),
    (
        "今晚和对象出去吃饭",
        '{"reply":"外面有点凉，那件你对象送的外套正好披上。","intent":"recommend",'
        '"occasion":"casual","item_ids":[12,30,41]}',
    ),
    (
        "今天穿什么",
        '{"reply":"看天气穿就行，我给你挑了三套。","intent":"recommend",'
        '"occasion":null,"item_ids":[12,30,41]}',
    ),
    (
        "谢谢",
        '{"reply":"不客气，随时喊我。","intent":"chat",'
        '"occasion":null,"item_ids":[]}',
    ),
]

HISTORY_LIMIT = 6
HISTORY_CHAR_LIMIT = 200
REPLY_CHAR_LIMIT = 120

# --- 从自然语言里抽「去哪儿」和「多少度」 ---------------------------------

LOCATION_MARKERS = (
    "在",
    "去",
    "到",
    "待",
    "这边",
    "那边",
    "的天气",
    "今天",
    "明天",
    "后天",
    "现在",
    "出差",
)
CITY_METAPHOR = ("像", "比", "跟")  # 「像北京那样冷」不是换城市
FAR_PLACES = (
    "澳洲",
    "澳大利亚",
    "日本",
    "韩国",
    "泰国",
    "新加坡",
    "马来西亚",
    "越南",
    "三亚",
    "海南",
    "香港",
    "澳门",
    "台湾",
    "美国",
    "加拿大",
    "英国",
    "法国",
    "德国",
    "意大利",
    "西班牙",
    "欧洲",
    "新西兰",
    "迪拜",
    "俄罗斯",
)
SHORT_MESSAGE = 12

RANGE_RE = re.compile(
    r"(?<!\d)(\d{1,2})(?!\d)\s*(?:到|至|-|~|—)\s*(?<!\d)(\d{1,2})(?!\d)\s*(?:度|℃)"
)
PAIR_RE = re.compile(r"(?<!\d)(\d{1,2})(?!\d)[^\d]{0,8}(?<!\d)(\d{1,2})(?!\d)\s*(?:度|℃)")
SINGLE_RE = re.compile(r"(?<!\d)(\d{1,2})(?!\d)\s*(?:度|℃)")


def _valid_temp(value: int) -> bool:
    return -30 <= value <= 45


def extract_temperature(message: str) -> tuple[float, float] | None:
    """从「15 到 25 度」「白天 25 晚上 15」「明天 5 度」里取温度范围。"""
    text = message

    match = RANGE_RE.search(text)
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        if _valid_temp(low) and _valid_temp(high):
            return (float(min(low, high)), float(max(low, high)))

    match = PAIR_RE.search(text)
    if match:
        first, second = int(match.group(1)), int(match.group(2))
        if _valid_temp(first) and _valid_temp(second):
            return (float(min(first, second)), float(max(first, second)))

    match = SINGLE_RE.search(text)
    if match:
        value = int(match.group(1))
        if _valid_temp(value):
            return (float(value), float(value))

    return None


def extract_city(message: str) -> str | None:
    """内置城市名；比喻句（像北京那样冷）不算，短句或带地点词才算。"""
    from .data.cities import city_names

    text = message.strip()
    for name in city_names():
        if name not in text:
            continue
        if any(f"{prefix}{name}" in text for prefix in CITY_METAPHOR):
            continue
        if len(text) <= SHORT_MESSAGE or any(marker in text for marker in LOCATION_MARKERS):
            return name
    return None


def extract_far_place(message: str) -> str | None:
    """8 城之外的地名：识别得到但拿不到天气时要说清楚，而不是拿默认城市硬算。"""
    text = message.strip()
    for name in FAR_PLACES:
        if name not in text:
            continue
        if any(f"{prefix}{name}" in text for prefix in CITY_METAPHOR):
            continue
        return name
    return None


def temperature_weather(low: float, high: float, city: str) -> WeatherResult:
    """用户直接给了温度：不取上游，用他的数字构造 facts（体感用温度近似）。"""
    snapshot = WeatherSnapshot(
        city=city,
        date=today_in("Asia/Shanghai"),
        t_min=low,
        t_max=high,
        feels_min=low,
        feels_max=high,
        precip_prob=0.0,
        wind=0.0,
        uv=0.0,
        weather_code=0,
    )
    return WeatherResult(
        snapshot=snapshot,
        cached=False,
        stale=False,
        observed_at=snapshot.date,
        fetched_at=now_iso(),
    )


@dataclass
class ParsedIntent:
    intent: str = "recommend"
    occasion: str | None = None
    scene: str = ""
    # 规则层判定够确定时锁定意图，模型只能细化（场合/选品）不能推翻
    locked: bool = False


def parse_intent_rules(message: str) -> ParsedIntent:
    text = message.strip().lower()

    occasion: str | None = None
    scene = ""
    for value, words in OCCASION_WORDS.items():
        hit = next((word for word in words if word in text), None)
        if hit:
            occasion = value
            scene = hit
            break

    # 寒暄优先，但句子里夹了天气/场合/推荐词就不是纯寒暄
    if any(word in text for word in GREETING_WORDS) and not any(
        word in text for word in INTENT_GUARD_WORDS
    ):
        return ParsedIntent(intent="chat", occasion=None, scene="", locked=True)

    # 穿着词最硬：既问了穿什么，就一定要出搭配，不能被天气词带走
    if any(word in text for word in CLOTHING_WORDS):
        return ParsedIntent(intent="recommend", occasion=occasion, scene=scene, locked=True)

    if any(word in text for word in WEATHER_WORDS):
        return ParsedIntent(intent="weather", occasion=occasion, scene=scene, locked=True)
    if any(word in text for word in REROLL_WORDS):
        return ParsedIntent(intent="reroll", occasion=occasion, scene=scene, locked=True)
    # 都没命中：交给模型判，模型可以选 chat / recommend / weather
    return ParsedIntent(intent="recommend", occasion=occasion, scene=scene, locked=False)


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
    "chat": ("get_weather",),
    "weather": ("get_weather",),
}


def _template_reply(
    intent: str, occasion: str | None, scene: str, ctx: ToolContext, scope: str | None = None
) -> str:
    if intent == "chat":
        return "你好呀，今天想穿点什么？"
    text = _base_template(intent, occasion, scene, ctx)
    return f"{text}（{scope}）" if scope else text


def _base_template(intent: str, occasion: str | None, scene: str, ctx: ToolContext) -> str:
    if intent == "weather" and ctx.weather is not None:
        snap = ctx.weather.snapshot
        return (
            f"{snap.city}今天{weather_text(snap.weather_code)}，"
            f"{snap.t_min:.1f}–{snap.t_max:.1f}℃，"
            f"体感 {snap.feels_min:.1f}–{snap.feels_max:.1f}℃"
        )
    scene = scene or (OCCASION_LABEL[occasion] if occasion else "")
    if intent == "reroll":
        return f"换一套，还是{scene}" if scene else "换一套，再看看"
    if occasion:
        return f"正在衣柜里为你挑适合{scene}的搭配"
    return "正在衣柜里为你挑今天能穿的搭配"


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text[:limit]


RELAX_PHRASES = {"随便配一套", "随便配一套吧", "随便搭一套"}


def _empty_outfit_reply(ctx: ToolContext) -> str:
    """凑不齐一套时，用真实件数拼一句有用的建议——这句绝不让模型写。"""
    usable = filter_usable(ctx.rule_items, ctx.occasion)
    counts: dict[str, int] = {}
    for item in usable:
        counts[item.category] = counts.get(item.category, 0) + 1

    label = OCCASION_LABEL.get(ctx.occasion or "", "这个场景")

    if not usable:
        return (
            f"{label}的场景你现在一件能穿的都没有（{len(ctx.rows)} 件里都标给了别的场合）。"
            "可以把几件通用款的场合留空，或者先补几件。"
        )

    tops = counts.get("top", 0) + counts.get("dress", 0)
    bottoms = counts.get("bottom", 0) + counts.get("dress", 0)
    shoes = counts.get("shoes", 0)

    want_outer = bool(ctx.weather and need_outer(ctx.weather.snapshot.feels_min))
    needs: list[tuple[str, str]] = [
        ("top", "上衣或连衣裙"),
        ("bottom", "下装"),
        ("shoes", "鞋"),
    ]
    if want_outer:
        needs.append(("outer", "外套"))

    missing = [
        (name, counts.get(category, 0))
        for category, name in needs
        if counts.get(category, 0) == 0
    ]
    if missing:
        advice = missing[0][0]
    else:
        advice = min(
            [
                ("上衣或连衣裙", tops),
                ("下装", bottoms),
                ("鞋", shoes),
            ],
            key=lambda pair: pair[1],
        )[0]

    return (
        f"{label}的话你只有 {tops} 件能穿的上衣、{bottoms} 件下装、{shoes} 双鞋，"
        f"还凑不齐一套。要么先补{advice}，要么我按现有这些随便配一套给你看？"
    )


def _relaxed_reply(ctx: ToolContext) -> str:
    """场合不足兜底出套时的诚实说明：不假装这些都是专门为该场合的。"""
    label = OCCASION_LABEL.get(ctx.occasion or "", "这个场景")
    return f"专门为{label}场合的衣服不太够，这几套里有些不是专门为{label}的，你看着挑。"


def _history_messages(payload: ChatIn) -> list[dict]:
    history = payload.history[-HISTORY_LIMIT:]
    return [
        {"role": msg.role, "content": _clip(msg.content, HISTORY_CHAR_LIMIT)}
        for msg in history
        if msg.content.strip()
    ]


def _user_prompt(message: str, ctx: ToolContext, pool: list[RuleItem], weather_note: str) -> str:
    lines = [
        f"用户这句话：{message}",
        "",
        f"今天天气：{weather_note}",
        f"场合线索：{ctx.occasion or '未提'}",
        "",
        "候选单品（只能从这里选 id）：",
    ]
    for item in pool:
        line = (
            f"- id={item.id} category={item.category} warmth={item.warmth} formality={item.formality}"
        )
        if item.note:
            line += f" 备注：{clean_note(item.note)}"
        lines.append(line)
    if not pool:
        lines.append("（衣橱里暂时没有可用单品）")
    lines.append("")
    lines.append("请按 JSON 输出。闲聊或问天气时 item_ids 给空数组。")
    return "\n".join(lines)


def _rules_outfits(ctx: ToolContext) -> list[RecommendOutfitOut]:
    plan = ctx.plan
    if plan is None or not getattr(plan, "outfits", None):
        return []
    thumbs = {row.id: primary_thumb(row) for row in ctx.rows}
    return [
        recommend_service.outfit_out(
            outfit.items, outfit.reason, thumbs, relaxed_occasion=outfit.relaxed_occasion
        )
        for outfit in plan.outfits
    ]


def _with_model_outfit(
    chosen: list[RuleItem], reply: str, ctx: ToolContext, rules: list[RecommendOutfitOut]
) -> list[RecommendOutfitOut]:
    thumbs = {row.id: primary_thumb(row) for row in ctx.rows}
    first = recommend_service.outfit_out(chosen, "按你的话挑的", thumbs)
    return [first] + rules[1:]


async def _ask_model(
    config: LLMConfig,
    messages: list[dict],
) -> dict:
    data, _usage = await chat_json_messages(config, messages)
    return data


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
    # 「按现有的配一套」：放宽到不限场合再试一次
    relaxed = message in RELAX_PHRASES
    config = resolve_llm_config(x_llm_key)

    # 先抽用户自己说的地点与温度：温度 > 消息里的城市 > 前端传的 city > 默认
    temperature = extract_temperature(message)
    city_signal = extract_city(message)
    far_place = extract_far_place(message)

    ctx = ToolContext(
        db=db,
        city=city_signal or payload.city,
        occasion=None if relaxed else (payload.occasion or parsed.occasion),
        exclude_ids=list(payload.exclude_ids or []),
    )

    scope_note: str | None = None
    if temperature is not None:
        low, high = temperature
        ctx.weather = temperature_weather(low, high, city_signal or payload.city or "杭州")
        scope_note = (
            f"按你说的 {low:.0f} 度算的"
            if low == high
            else f"按你说的 {low:.0f}–{high:.0f} 度算的"
        )
    elif city_signal:
        scope_note = f"按{city_signal}的天气看"

    # 8 城之外的地名：不给假数据，问温度（南半球 12 月是夏天，拿北京冬天推羽绒服是硬错误）
    if far_place and temperature is None:
        return ChatOut(
            reply=(
                f"我只有这 8 个城市的天气，{far_place}取不到。"
                "你到那边大概几度？告诉我温度我就能配。"
            ),
            intent="recommend",
            occasion=ctx.occasion,
            trace=[],
            outfits=[],
            source="none",
            fallback_reason="weather_unavailable",
        )

    trace: list[ChatTraceStep] = []

    # 有 key 时统一跑完整链路（模型可能把「推荐」改判成「闲聊」，池子先备好）
    chain = CHAINS[parsed.intent] if config is None else CHAINS["recommend"]
    if temperature is not None:
        # 用户给了温度就不取上游
        chain = tuple(name for name in chain if name != "get_weather")
    for name in chain:
        started = time.perf_counter()
        try:
            summary, _payload = await TOOLS[name](ctx)
        except HTTPException:
            # 有 key 的闲聊不该因为天气挂了就 502；没 key 时保持原语义（向上抛）
            if config is None or name != "get_weather":
                raise
            summary = "天气暂时取不到"
            ctx.weather = None
            break
        trace.append(
            ChatTraceStep(
                tool=name, summary=summary, ms=int((time.perf_counter() - started) * 1000)
            )
        )

    if config is None:
        # 降级路径：模板回复，行为和之前一致
        if parsed.intent == "weather":
            return ChatOut(
                reply=_template_reply("weather", ctx.occasion, parsed.scene, ctx, scope_note),
                intent="weather",
                occasion=ctx.occasion,
                trace=trace,
                outfits=[],
                source="rules",
                fallback_reason=None,
            )
        rules_now = _rules_outfits(ctx)
        return ChatOut(
            reply=(
                _empty_outfit_reply(ctx)
                if parsed.intent == "recommend" and not rules_now
                else _template_reply(parsed.intent, ctx.occasion, parsed.scene, ctx, scope_note)
            ),
            intent=parsed.intent,
            occasion=ctx.occasion,
            trace=trace,
            outfits=rules_now,
            source="rules",
            fallback_reason=None,
        )

    # --- 有 key：一次调用同时拿回复 + 意图 + 选品 ---
    rules_outfits = _rules_outfits(ctx)
    snap = ctx.weather.snapshot if ctx.weather else None
    facts = (
        WeatherFacts(date=snap.date, feels_min=snap.feels_min, feels_max=snap.feels_max)
        if snap
        else WeatherFacts(date="", feels_min=18.0, feels_max=22.0)
    )
    pool = build_pool(facts, ctx.rule_items, ctx.occasion) if ctx.rule_items else []
    weather_note = (
        f"{snap.city} {weather_text(snap.weather_code)} {snap.t_min:.1f}–{snap.t_max:.1f}℃"
        if snap
        else "暂时取不到"
    )
    if scope_note:
        weather_note = f"{weather_note}（{scope_note}）"

    messages: list[dict] = [{"role": "system", "content": PERSONA}]
    for user_text, assistant_text in FEW_SHOT:
        messages.append({"role": "user", "content": user_text})
        messages.append({"role": "assistant", "content": assistant_text})
    messages.extend(_history_messages(payload))
    messages.append({"role": "user", "content": _user_prompt(message, ctx, pool, weather_note)})

    model_started = time.perf_counter()
    try:
        data = await _ask_model(config, messages)
    except LLMError as exc:
        # 只记有没有备注，不记备注内容（私人信息）
        logger.warning(
            "chat model failed reason=%s has_note=%s",
            exc.reason,
            any(item.note for item in ctx.rule_items),
        )
        trace.append(
            ChatTraceStep(
                tool="model",
                summary=f"模型失败（{exc.reason}）",
                ms=int((time.perf_counter() - model_started) * 1000),
            )
        )
        return ChatOut(
            reply=(
                _empty_outfit_reply(ctx)
                if parsed.intent == "recommend" and not rules_outfits
                else _template_reply(parsed.intent, ctx.occasion, parsed.scene, ctx, scope_note)
            ),
            intent=parsed.intent,
            occasion=ctx.occasion,
            trace=trace,
            outfits=rules_outfits,
            source="rules",
            fallback_reason=exc.reason,
        )

    intent = data.get("intent")
    reply = _clip(str(data.get("reply") or ""), REPLY_CHAR_LIMIT)
    occasion = data.get("occasion")
    raw_ids = data.get("item_ids")

    def finish(
        *, final_intent: str, outfits: list[RecommendOutfitOut], source: str, reason: str | None
    ) -> ChatOut:
        trace.append(
            ChatTraceStep(
                tool="model",
                summary=f"回复 {len(reply)} 字" if reply else "模型没给回复",
                ms=int((time.perf_counter() - model_started) * 1000),
            )
        )
        text = reply or _template_reply(final_intent, ctx.occasion, parsed.scene, ctx, scope_note)
        # 推荐意图但组不出套：丢掉模型那句话，用真实件数拼的建议（模型会编、会说空话）
        has_relaxed = any(getattr(o, "relaxed_occasion", False) for o in outfits)
        if final_intent == "recommend" and not outfits:
            text = _empty_outfit_reply(ctx)
        elif final_intent == "recommend" and has_relaxed:
            text = _relaxed_reply(ctx)
        return ChatOut(
            reply=text,
            intent=final_intent,
            occasion=ctx.occasion,
            trace=trace,
            outfits=outfits,
            source=source,
            fallback_reason=reason,
        )

    # 规则层锁定意图时，模型只能细化（场合/选品），不能推翻
    model_intent = intent if intent in INTENTS else None
    if occasion is not None and occasion not in OCCASIONS:
        model_intent = None  # 场合越界视为整条不可信

    final_intent = parsed.intent if parsed.locked else model_intent

    # 规则没锁定、模型也判不出来 → 走规则结果
    if final_intent is None:
        rules_now = rules_outfits
        return ChatOut(
            reply=(
                _empty_outfit_reply(ctx)
                if parsed.intent == "recommend" and not rules_now
                else _template_reply(parsed.intent, ctx.occasion, parsed.scene, ctx, scope_note)
            ),
            intent=parsed.intent,
            occasion=ctx.occasion,
            trace=trace
            + [
                ChatTraceStep(
                    tool="model",
                    summary="输出越界，已丢弃",
                    ms=int((time.perf_counter() - model_started) * 1000),
                )
            ],
            outfits=rules_now,
            source="rules",
            fallback_reason="invalid_intent",
        )

    if occasion and not relaxed:
        ctx.occasion = occasion

    if final_intent in ("chat", "weather"):
        # 这两个意图不该带选品；带了就忽略
        return finish(final_intent=final_intent, outfits=[], source="llm", reason=None)

    want_outer = need_outer(snap.feels_min) if snap else False
    chosen, problems = validate_selection({"item_ids": raw_ids}, pool, want_outer)

    if chosen is None and problems:
        repair_messages = messages + [
            {"role": "assistant", "content": str(data)},
            {
                "role": "user",
                "content": (
                    f"这次输出不合规：{'；'.join(problems)}。"
                    "请只修正 item_ids（必须全部来自候选池、3–6 件、不重复、含上装/下装或裙装/鞋），"
                    "reply 保持不变，重新输出 JSON。"
                ),
            },
        ]
        try:
            data = await _ask_model(config, repair_messages)
            reply = _clip(str(data.get("reply") or reply), REPLY_CHAR_LIMIT)
            raw_ids = data.get("item_ids")
            chosen, problems = validate_selection({"item_ids": raw_ids}, pool, want_outer)
        except LLMError:
            chosen, problems = None, problems or ["修复调用失败"]

    if chosen is None:
        # 重试仍不合格：用规则结果，但保留模型写的回复
        return finish(
            final_intent=final_intent, outfits=rules_outfits, source="rules", reason="invalid_ids"
        )

    return finish(
        final_intent=final_intent,
        outfits=_with_model_outfit(chosen, reply, ctx, rules_outfits),
        source="llm",
        reason=None,
    )
