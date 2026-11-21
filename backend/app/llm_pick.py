"""从规则候选里让模型挑一套：候选池 → prompt → 校验 → 一次修复 → 降级。

这里最值钱的不是 prompt，是校验：模型编造 id 是必然事件，
所以只信「候选池内 + 结构合法 + 品类齐全」，不信提示词里的「不许发明」。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .llm import LLMConfig, LLMError, chat_json, key_fingerprint
from .rules import (
    RuleItem,
    WeatherFacts,
    build_outfits,
    filter_usable,
    formality_of,
    layer_of,
    need_outer,
    need_warmth,
    rank_items,
)

logger = logging.getLogger(__name__)

# 每类取前几件进池子，总数控制在 10–15。dress 必须在这里，否则「只有连衣裙」的衣橱
# 会被判成 missing_category，LLM 路径比规则路径更严格——那是缺陷，不是设计。
POOL_SIZES: dict[str, int] = {
    "top": 4,
    "bottom": 3,
    "dress": 2,
    "shoes": 3,
    "outer": 3,
    "accessory": 2,
}

MIN_ITEMS = 3
MAX_ITEMS = 6

SYSTEM_PROMPT = (
    "你是一个穿搭助手。根据天气和场合，从给定的候选单品里挑出一套完整搭配。"
    "只能使用候选列表里出现过的 id，绝对不要编造 id。"
    "只输出 JSON，形如 {\"item_ids\": [1, 2, 3], \"reason\": \"一句中文理由\"}。"
)


@dataclass(frozen=True)
class PickResult:
    outfit: tuple[RuleItem, ...]
    reason: str
    source: str  # "llm" | "rules"
    attempts: int
    fallback_reason: str | None = None
    usage: dict[str, int | None] | None = None


def build_pool(facts: WeatherFacts, items: list[RuleItem], occasion: str | None) -> list[RuleItem]:
    """和规则同一套排序，只是每类截前几件。"""
    target_warmth = need_warmth(facts.feels_min)
    target_formality = formality_of(occasion)
    usable = filter_usable(items, occasion)

    pool: list[RuleItem] = []
    for category, size in POOL_SIZES.items():
        if category == "outer" and not need_outer(facts.feels_min):
            continue
        ranked = rank_items(
            [item for item in usable if item.category == category],
            target_warmth,
            target_formality,
        )
        pool.extend(ranked[:size])
    return pool


def validate_selection(
    payload: dict, pool: list[RuleItem], want_outer: bool
) -> tuple[list[RuleItem] | None, list[str]]:
    """返回 (选中的单品, 问题列表)。问题列表会原样回灌给模型。"""
    ids = payload.get("item_ids")
    if not isinstance(ids, list):
        return None, ["item_ids 必须是数组"]
    if any(isinstance(value, bool) or not isinstance(value, int) for value in ids):
        return None, ["item_ids 里必须全是整数 id"]

    problems: list[str] = []
    if not MIN_ITEMS <= len(ids) <= MAX_ITEMS:
        problems.append(f"件数要在 {MIN_ITEMS}–{MAX_ITEMS} 之间，当前 {len(ids)} 件")
    if len(set(ids)) != len(ids):
        problems.append("同一件单品不能重复出现")

    by_id = {item.id: item for item in pool}
    unknown = [value for value in ids if value not in by_id]
    if unknown:
        problems.append(f"这些 id 不在候选池里：{unknown}")
        return None, problems

    chosen = [by_id[value] for value in ids]
    categories = {item.category for item in chosen}
    if not {"top", "dress"} & categories:
        problems.append("缺少上衣或连衣裙")
    if not {"bottom", "dress"} & categories:
        problems.append("缺少下装或连衣裙")
    if "shoes" not in categories:
        problems.append("缺少鞋")
    if want_outer and "outer" not in categories:
        problems.append("天气需要外套，但没选外套")

    if problems:
        return None, problems
    return chosen, []


def build_user_prompt(
    facts: WeatherFacts, occasion: str | None, pool: list[RuleItem], want_outer: bool
) -> str:
    lines = [
        f"日期：{facts.date}",
        f"体感：{facts.feels_min:.1f}–{facts.feels_max:.1f}℃",
        f"需要的厚薄：{need_warmth(facts.feels_min)}（1 薄 / 2 中 / 3 厚）",
        f"需要外套：{'是' if want_outer else '否'}",
        f"场合：{occasion or '不限'}",
        "",
        "候选单品：",
    ]
    for item in pool:
        lines.append(
            f"- id={item.id} category={item.category} warmth={item.warmth} "
            f"layer={layer_of(item.category)} formality={formality_of(item.occasion)}"
        )
    lines.append("")
    lines.append("只能从上面给出的 id 中选，不许发明。输出 JSON。")
    return "\n".join(lines)


def _log(
    *, source: str, attempts: int, fallback: str | None, elapsed_ms: float, api_key: str | None
) -> None:
    logger.info(
        "llm_pick mode=llm source=%s attempts=%d fallback=%s elapsed_ms=%.0f key=%s",
        source,
        attempts,
        fallback or "-",
        elapsed_ms,
        key_fingerprint(api_key) if api_key else "-",
    )


def rules_fallback(
    facts: WeatherFacts,
    items: list[RuleItem],
    occasion: str | None,
    reason: str | None,
    attempts: int,
) -> PickResult:
    plan = build_outfits(facts, items, occasion)
    if not plan.outfits:
        return PickResult((), "", "rules", attempts, reason or "empty_wardrobe")
    first = plan.outfits[0]
    return PickResult(first.items, first.reason, "rules", attempts, reason)


async def pick_with_llm(
    config: LLMConfig,
    facts: WeatherFacts,
    items: list[RuleItem],
    occasion: str | None,
) -> PickResult:
    started = time.perf_counter()
    pool = build_pool(facts, items, occasion)
    # 只按池子里实际有的品类判断：缺基础件才跳过模型，别浪费时间问一个必然失败的问题
    categories_in_pool = {item.category for item in pool}
    needs_outer = need_outer(facts.feels_min)
    has_base = (
        bool({"top", "dress"} & categories_in_pool)
        and bool({"bottom", "dress"} & categories_in_pool)
        and "shoes" in categories_in_pool
    )
    has_outer = (not needs_outer) or "outer" in categories_in_pool
    want_outer = needs_outer

    if not pool or not has_base or not has_outer:
        elapsed = (time.perf_counter() - started) * 1000
        reason = "empty_pool" if not pool else "missing_category"
        _log(source="rules", attempts=0, fallback=reason, elapsed_ms=elapsed, api_key=config.api_key)
        return rules_fallback(facts, items, occasion, reason, 0)

    user_prompt = build_user_prompt(facts, occasion, pool, want_outer)
    problems: list[str] = []
    fallback_reason = "invalid_outfit"

    for attempt in (1, 2):
        prompt = user_prompt
        if attempt == 2:
            prompt = (
                f"{user_prompt}\n\n上一次的输出不合规：{'；'.join(problems)}\n"
                "请修正后重新输出 JSON。"
            )
        try:
            payload, usage = await chat_json(config, SYSTEM_PROMPT, prompt)
        except LLMError as exc:
            elapsed = (time.perf_counter() - started) * 1000
            _log(
                source="rules",
                attempts=attempt,
                fallback=exc.reason,
                elapsed_ms=elapsed,
                api_key=config.api_key,
            )
            return rules_fallback(facts, items, occasion, exc.reason, attempt)

        chosen, problems = validate_selection(payload, pool, want_outer)
        if chosen is not None:
            reason = str(payload.get("reason") or "").strip() or "按今天的天气和场合配的"
            elapsed = (time.perf_counter() - started) * 1000
            _log(source="llm", attempts=attempt, fallback=None, elapsed_ms=elapsed, api_key=config.api_key)
            return PickResult(tuple(chosen), reason, "llm", attempt, None, usage)

        fallback_reason = "invalid_ids" if any("候选池" in p for p in problems) else "invalid_outfit"

    elapsed = (time.perf_counter() - started) * 1000
    _log(source="rules", attempts=2, fallback=fallback_reason, elapsed_ms=elapsed, api_key=config.api_key)
    return rules_fallback(facts, items, occasion, fallback_reason, 2)
