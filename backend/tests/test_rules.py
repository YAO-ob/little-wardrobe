"""规则候选生成测试：全部用人造衣橱，不碰数据库、不打网络。"""

from __future__ import annotations

import pytest

from app import rules
from app.rules import (
    RecommendPlan,
    RuleItem,
    WeatherFacts,
    build_outfits,
    formality_level,
    formality_of,
    layer_from_category,
    layer_of,
    need_extra,
    need_outer,
    need_warmth,
)


def wardrobe() -> list[RuleItem]:
    """一套够用的合成衣橱：每类都有冷/中/热三档，覆盖常见情形。"""
    return [
        RuleItem(1, "top", 1, "casual"),
        RuleItem(2, "top", 2, "casual"),
        RuleItem(3, "top", 3, "casual"),
        RuleItem(4, "top", 2, None),
        RuleItem(10, "bottom", 2, "casual"),
        RuleItem(11, "bottom", 3, "work"),
        RuleItem(12, "bottom", 1, "sport"),
        RuleItem(13, "bottom", 2, None),
        RuleItem(20, "shoes", 2, "casual"),
        RuleItem(21, "shoes", 2, "sport"),
        RuleItem(22, "shoes", 2, None),
        RuleItem(30, "outer", 3, "casual"),
        RuleItem(31, "outer", 2, None),
        RuleItem(40, "accessory", 1, None),
        RuleItem(41, "accessory", 2, "work"),
    ]


def cold() -> WeatherFacts:
    return WeatherFacts(date="2026-11-21", feels_min=-5.0, feels_max=3.0)


def hot() -> WeatherFacts:
    return WeatherFacts(date="2026-07-21", feels_min=30.0, feels_max=36.0)


def categories(outfit) -> set[str]:
    return {item.category for item in outfit.items}


# --- 阈值函数 -------------------------------------------------------------


def test_need_warmth_thresholds():
    assert need_warmth(-5) == 3
    assert need_warmth(6.9) == 3
    assert need_warmth(7.0) == 2
    assert need_warmth(16.9) == 2
    assert need_warmth(17.0) == 1
    assert need_warmth(30) == 1


def test_hysteresis_raised_cold_boundary():
    """体感 6.5 按旧阈值（5）会给 2，新阈值（7）必须是 3。"""
    assert rules.COLD_FEELS_MIN == 7.0
    assert need_warmth(6.5) == 3


def test_hysteresis_raised_mild_boundary():
    """体感 16.0 按旧阈值（15）会给 1，新阈值（17）必须是 2。"""
    assert rules.MILD_FEELS_MIN == 17.0
    assert need_warmth(16.0) == 2


def test_need_outer_threshold():
    assert need_outer(11.9) is True
    assert need_outer(12.0) is False


def test_need_extra_requires_both_spread_and_cool_morning():
    assert need_extra(10.0, 20.0) is True  # 温差 10 ≥ 9，早间 10 < 18
    assert need_extra(10.0, 18.0) is False  # 温差 8，不够
    assert need_extra(19.0, 30.0) is False  # 早间不够凉
    assert need_extra(5.0, 30.0) is True


def test_layer_and_formality_derivation():
    assert layer_from_category("outer") == "outer"
    assert layer_from_category("top") == "inner"
    assert layer_from_category("dress") == "inner"
    assert layer_from_category("bottom") is None
    assert layer_from_category("shoes") is None
    assert layer_from_category("accessory") is None

    assert formality_of("work") == 4
    assert formality_of("formal") == 5
    assert formality_of("sport") == 1
    assert formality_of("casual") == 2
    assert formality_of(None) == 2


def test_stored_layer_wins_over_category():
    """用户补录了 layer，就按补录的算；没填才按品类推导。"""
    assert layer_of(RuleItem(1, "top", 2, "casual", layer="outer")) == "outer"
    assert layer_of(RuleItem(2, "top", 2, "casual")) == "inner"
    assert layer_of(RuleItem(3, "outer", 3, "casual", layer=None)) == "outer"


def test_stored_formality_wins_over_occasion():
    assert formality_level(RuleItem(1, "top", 2, "casual", formality=5)) == 5
    assert formality_level(RuleItem(2, "top", 2, "casual")) == 2
    assert formality_level(RuleItem(3, "top", 2, "work")) == 4


def test_stored_formality_changes_ranking():
    """同一场合下，补录了正式度的单品排序要跟着变。"""
    plain = RuleItem(1, "top", 2, None)  # 场合为空 → 推导正式度 2
    formal = RuleItem(2, "top", 2, None, formality=5)  # 存量 5

    plan = build_outfits(
        WeatherFacts(date="2026-11-22", feels_min=9.0, feels_max=15.0),
        [plain, formal, RuleItem(10, "bottom", 2, None), RuleItem(20, "shoes", 2, None)],
        occasion="formal",
    )

    first_top = next(item for item in plan.outfits[0].items if item.category == "top")
    assert first_top.id == 2  # formal 目标 5，存了 5 的那件排前面


# --- 极端温度 -------------------------------------------------------------


def test_cold_weather_every_outfit_has_outer():
    plan = build_outfits(cold(), wardrobe())
    assert len(plan.outfits) == 3
    for outfit in plan.outfits:
        assert "outer" in categories(outfit)


def test_hot_weather_has_no_outer_and_no_thick_items():
    plan = build_outfits(hot(), wardrobe())
    assert len(plan.outfits) == 3
    for outfit in plan.outfits:
        assert "outer" not in categories(outfit)
        for item in outfit.items:
            assert item.warmth != 3, f"热天不该出现厚单品：{item}"


def test_hot_weather_prefers_thin_items():
    plan = build_outfits(hot(), wardrobe())
    tops = [item for outfit in plan.outfits for item in outfit.items if item.category == "top"]
    assert tops
    assert all(item.warmth == 1 for item in tops)


# --- 缺品类 ---------------------------------------------------------------


def test_missing_bottom_reduces_outfits_and_says_so():
    items = [item for item in wardrobe() if item.category != "bottom"]
    plan = build_outfits(cold(), items)

    assert plan.outfits == ()
    assert plan.notice is not None
    assert "下装" in plan.notice


def test_missing_bottom_but_has_dress_still_works():
    items = [item for item in wardrobe() if item.category != "bottom"]
    items.append(RuleItem(50, "dress", 2, "casual"))

    plan = build_outfits(cold(), items)
    assert len(plan.outfits) >= 1
    for outfit in plan.outfits:
        assert "dress" in categories(outfit)
    # 有连衣裙兜底时不算「缺下装」，不该报缺口；重点是别抛异常、别 0 套
    assert plan.notice is None or "下装" in plan.notice


def test_empty_wardrobe_returns_zero_without_raising():
    plan = build_outfits(cold(), [])
    assert isinstance(plan, RecommendPlan)
    assert plan.outfits == ()
    assert plan.notice and ("上衣" in plan.notice or "下装" in plan.notice)


def test_missing_shoes_yields_nothing_and_mentions_shoes():
    items = [item for item in wardrobe() if item.category != "shoes"]
    plan = build_outfits(cold(), items)
    assert plan.outfits == ()
    assert plan.notice is not None and "鞋" in plan.notice


def test_cold_without_outer_still_returns_outfits_with_notice():
    items = [item for item in wardrobe() if item.category != "outer"]
    plan = build_outfits(cold(), items)
    assert len(plan.outfits) >= 1
    assert plan.notice is not None and "外套" in plan.notice


# --- 场合过滤 -------------------------------------------------------------


def test_work_excludes_sport_only_items():
    items = wardrobe()
    items.append(RuleItem(60, "top", 2, "sport"))  # sport 专属
    plan = build_outfits(
        WeatherFacts(date="2026-11-21", feels_min=12.0, feels_max=18.0),
        items,
        occasion="work",
    )

    ids = {item.id for outfit in plan.outfits for item in outfit.items}
    assert 60 not in ids  # sport 专属不能混进通勤
    for outfit in plan.outfits:
        for item in outfit.items:
            assert item.occasion in (None, "", "work")


def test_sport_occasion_allows_empty_and_sport_items():
    plan = build_outfits(
        WeatherFacts(date="2026-11-21", feels_min=15.0, feels_max=20.0),
        wardrobe(),
        occasion="sport",
    )
    assert plan.outfits
    ids = {item.id for outfit in plan.outfits for item in outfit.items}
    assert 12 in ids or 21 in ids  # sport 单品有机会入选


# --- 组合约束 -------------------------------------------------------------


def test_three_outfits_are_distinct():
    plan = build_outfits(cold(), wardrobe())
    sets = [frozenset(item.id for item in outfit.items) for outfit in plan.outfits]
    assert len(sets) == 3
    assert len(set(sets)) == 3
    for left in range(len(sets)):
        for right in range(left + 1, len(sets)):
            assert sets[left] != sets[right]


def test_no_duplicate_item_within_outfit():
    plan = build_outfits(cold(), wardrobe())
    for outfit in plan.outfits:
        ids = [item.id for item in outfit.items]
        assert len(ids) == len(set(ids))


def test_outfit_has_base_pieces():
    plan = build_outfits(cold(), wardrobe())
    for outfit in plan.outfits:
        cats = categories(outfit)
        assert {"top", "bottom", "shoes"} <= cats


def test_extra_layer_added_when_temperature_swings():
    facts = WeatherFacts(date="2026-11-21", feels_min=8.0, feels_max=22.0)
    assert need_extra(facts.feels_min, facts.feels_max)
    plan = build_outfits(facts, wardrobe())
    assert plan.outfits
    for outfit in plan.outfits:
        tops = [item for item in outfit.items if item.category == "top"]
        assert len(tops) == 2, "温差大时应有两层上衣"


def test_reason_mentions_feels_range():
    plan = build_outfits(cold(), wardrobe())
    assert plan.outfits
    for outfit in plan.outfits:
        assert "-5.0–3.0℃" in outfit.reason
        assert outfit.reason.endswith("配了外套") or "外套" in outfit.reason


def test_unknown_occasion_is_neutral():
    plan = build_outfits(hot(), wardrobe(), occasion=None)
    assert len(plan.outfits) == 3
    assert plan.notice is None


def test_stable_across_runs():
    first = build_outfits(cold(), wardrobe())
    second = build_outfits(cold(), list(reversed(wardrobe())))
    assert [o.items for o in first.outfits] == [o.items for o in second.outfits]


def test_thresholds_live_in_constants():
    assert rules.COLD_FEELS_MIN == 7.0
    assert rules.MILD_FEELS_MIN == 17.0
    assert rules.OUTER_FEELS_MIN == 12.0
    assert rules.DIFF_SPREAD == 9.0
    assert rules.DIFF_FEELS_MIN == 18.0


@pytest.mark.parametrize("occ", ["casual", "work", "sport", "formal"])
def test_all_occasions_produce_outfits(occ):
    plan = build_outfits(cold(), wardrobe(), occasion=occ)
    assert len(plan.outfits) >= 1


# --- 三套要有实质差异 -----------------------------------------------------


def diverse_wardrobe() -> list[RuleItem]:
    """top 6 / bottom 3 / outer 3 / shoes 3，够组出三套不重样的。"""
    items: list[RuleItem] = []
    items += [RuleItem(100 + i, "top", 2, "casual") for i in range(6)]
    items += [RuleItem(200 + i, "bottom", 2, "casual") for i in range(3)]
    items += [RuleItem(300 + i, "outer", 3, "casual") for i in range(3)]
    items += [RuleItem(400 + i, "shoes", 2, "casual") for i in range(3)]
    return items


def base_pairs(plan) -> list[tuple[int | None, int | None]]:
    pairs = []
    for outfit in plan.outfits:
        bottom = next((i.id for i in outfit.items if i.category == "bottom"), None)
        dress = next((i.id for i in outfit.items if i.category == "dress"), None)
        shoes = next((i.id for i in outfit.items if i.category == "shoes"), None)
        pairs.append((bottom or dress, shoes))
    return pairs


def test_three_outfits_differ_in_bottom_or_shoes():
    facts = WeatherFacts(date="2026-11-21", feels_min=9.0, feels_max=15.0)
    plan = build_outfits(facts, diverse_wardrobe())

    assert len(plan.outfits) == 3
    pairs = base_pairs(plan)
    distinct = {pair for pair in pairs}
    assert len(distinct) == 3, f"三套的下装/鞋组合应互不相同，实际 {pairs}"


def test_single_bottom_still_returns_three_outfits():
    """只有 1 条下装 + 1 双鞋时组合会重复，但必须仍给 3 套，不能报错或返空。"""
    items = [
        RuleItem(1, "top", 2, "casual"),
        RuleItem(2, "top", 2, "casual"),
        RuleItem(3, "top", 2, "casual"),
        RuleItem(10, "bottom", 2, "casual"),
        RuleItem(20, "shoes", 2, "casual"),
    ]
    plan = build_outfits(WeatherFacts(date="2026-11-21", feels_min=9.0, feels_max=15.0), items)

    assert len(plan.outfits) == 3
    for outfit in plan.outfits:
        assert {"top", "bottom", "shoes"} <= categories(outfit)
