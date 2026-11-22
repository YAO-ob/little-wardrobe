"""规则候选生成：纯函数，不碰数据库、不发请求。

输入是 dataclass（天气事实 + 单品摘要 + 场合），输出是结构化的搭配方案。
路由层负责把库里的 Item 映射成 RuleItem、把结果拼成响应。

为什么 layer / formality 要在这里推导：库里这两列目前 100% 为空
（极速录入没收这两项），放着不用等于白设计。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- 阈值常量（改这里，不要散落魔法数） -----------------------------------

# 体感低于此值 → 需要最厚一层（warmth 3）
# 取 7 而不是 5：不同天气模型之间差 ±2–3℃，硬边界会让同一天在边界上反复翻档；
# 穿搭场景下宁可穿厚，所以把「冷」的门槛抬高一点（迟滞）。
COLD_FEELS_MIN = 7.0
# 体感低于此值 → 中等厚薄（warmth 2），否则薄（warmth 1）
# 同样为了迟滞从 15 提到 17：小幅降温不该让整套从「中」跳到「薄」。
MILD_FEELS_MIN = 17.0
# 早间体感低于此值 → 需要外套
OUTER_FEELS_MIN = 12.0
# 昼夜温差 ≥ 此值，且早间体感低于 DIFF_FEELS_MIN → 加一层打底
DIFF_SPREAD = 9.0
DIFF_FEELS_MIN = 18.0

MAX_OUTFITS = 3

CATEGORY_LABELS = {
    "top": "上衣",
    "outer": "外套",
    "bottom": "下装",
    "shoes": "鞋",
    "accessory": "配饰",
    "dress": "连衣裙",
}

WARMTH_LABELS = {1: "薄", 2: "中", 3: "厚"}

OCCASION_LABELS = {
    "casual": "日常",
    "work": "通勤",
    "sport": "运动",
    "formal": "正式",
}

# 图层：只有这三类参与「内/中/外」，下装鞋配饰不参与
LAYER_BY_CATEGORY = {
    "outer": "outer",
    "top": "inner",
    "dress": "inner",
    "bottom": None,
    "shoes": None,
    "accessory": None,
}

FORMALITY_BY_OCCASION = {
    "work": 4,
    "formal": 5,
    "sport": 1,
    "casual": 2,
}

# 理由里从上到下的叙述顺序
REASON_ORDER = ("dress", "top", "outer", "bottom", "shoes", "accessory")


@dataclass(frozen=True)
class RuleItem:
    id: int
    category: str
    warmth: int | None = None
    occasion: list[str] = field(default_factory=list)
    # 下面两项：库里存了就优先用，没存才按品类/场合推导
    formality: int | None = None
    layer: str | None = None
    # 用户备注：只有模型看得懂它（规则路径不用）。截断 60 字、去掉换行
    note: str | None = None


NOTE_LIMIT = 60


def clean_note(raw: str | None) -> str | None:
    if not raw:
        return None
    text = " ".join(raw.split())
    return text[:NOTE_LIMIT] or None


@dataclass(frozen=True)
class WeatherFacts:
    date: str
    feels_min: float
    feels_max: float


@dataclass(frozen=True)
class OutfitPlan:
    items: tuple[RuleItem, ...]
    reason: str
    # true = 这套是场合不足时放宽组出的，掺了不是专门为目标场合的单品
    relaxed_occasion: bool = False


@dataclass(frozen=True)
class RecommendPlan:
    outfits: tuple[OutfitPlan, ...]
    notice: str | None


def layer_from_category(category: str) -> str | None:
    return LAYER_BY_CATEGORY.get(category)


def layer_of(item: RuleItem) -> str | None:
    """存量优先：用户补录过 layer 就用它，没填才按品类推导。"""
    return item.layer or layer_from_category(item.category)


def formality_of(occasion: str | None) -> int:
    """场合 → 正式度（用于「目标正式度」）。"""
    return FORMALITY_BY_OCCASION.get(occasion or "", 2)


def formality_level(item: RuleItem, target_formality: int | None = None) -> int:
    """存量优先：用户填了正式度就用它，没填才按场合推导。

    多场合时取与目标正式度最接近的那个——用户选了「通勤」，
    一件标了 [日常, 通勤] 的衣服在通勤场景下就按通勤的正式度算，
    不会被平均或取第一个拉低排名。
    """
    if item.formality is not None:
        return item.formality
    occasions = item.occasion or []
    if not occasions:
        return 2  # 没场合按日常算
    if target_formality is not None:
        return min(
            (formality_of(o) for o in occasions), key=lambda f: abs(f - target_formality)
        )
    return formality_of(occasions[0])


def need_warmth(feels_min: float) -> int:
    if feels_min < COLD_FEELS_MIN:
        return 3
    if feels_min < MILD_FEELS_MIN:
        return 2
    return 1


def need_outer(feels_min: float) -> bool:
    return feels_min < OUTER_FEELS_MIN


def need_extra(feels_min: float, feels_max: float) -> bool:
    """早晚温差大且早上凉，才值得多一层打底。"""
    return (feels_max - feels_min) >= DIFF_SPREAD and feels_min < DIFF_FEELS_MIN


def _warmth(item: RuleItem) -> int:
    """没填厚薄的按「中」算，避免直接排除掉半柜子数据。"""
    return item.warmth if item.warmth is not None else 2


def _item_key(item: RuleItem, target_warmth: int, target_formality: int) -> tuple[int, int, int]:
    item_formality = formality_level(item, target_formality)
    return (
        abs(_warmth(item) - target_warmth),
        abs(item_formality - target_formality),
        item.id,
    )


def _rank(items: list[RuleItem], target_warmth: int, target_formality: int) -> list[RuleItem]:
    return sorted(items, key=lambda item: _item_key(item, target_warmth, target_formality))


def _usable(item: RuleItem, occasion: str | None) -> bool:
    """目标场合为空 = 不过滤；衣服没标场合 = 任何场合可用；否则目标场合须在衣服场合列表里。"""
    if not occasion:
        return True
    return not item.occasion or occasion in item.occasion


def filter_usable(items: list[RuleItem], occasion: str | None) -> list[RuleItem]:
    return [item for item in items if _usable(item, occasion)]


def rank_items(
    items: list[RuleItem], target_warmth: int, target_formality: int
) -> list[RuleItem]:
    """按 (厚薄距离, 正式度距离, id) 排序。规则与 LLM 候选池共用这一处。"""
    return sorted(items, key=lambda item: _item_key(item, target_warmth, target_formality))


def _decorate(
    base: list[RuleItem],
    *,
    tops: list[RuleItem],
    outers: list[RuleItem],
    accessories: list[RuleItem],
    want_outer: bool,
    want_extra: bool,
    target_warmth: int,
) -> list[RuleItem]:
    chosen = list(base)
    used = {item.id for item in chosen}

    if want_outer and outers:
        for outer in outers:
            if outer.id not in used:
                chosen.append(outer)
                used.add(outer.id)
                break

    if want_extra:
        # 温差大时补一层比目标薄一档的打底
        for top in tops:
            if top.id in used:
                continue
            if _warmth(top) <= target_warmth - 1:
                chosen.append(top)
                used.add(top.id)
                break

    if accessories:
        for accessory in accessories:
            if accessory.id not in used:
                chosen.append(accessory)
                used.add(accessory.id)
                break

    return chosen


def _reason(facts: WeatherFacts, items: list[RuleItem], *, want_outer: bool, want_extra: bool) -> str:
    by_category: dict[str, list[RuleItem]] = {}
    for item in items:
        by_category.setdefault(item.category, []).append(item)

    parts: list[str] = []
    for category in REASON_ORDER:
        seen = 0
        for item in by_category.get(category, []):
            seen += 1
            warmth = WARMTH_LABELS.get(_warmth(item), "")
            if category == "top" and seen > 1:
                # 第二件上衣是温差大时补的打底，别写成「上衣 + 上衣」
                parts.append(f"{warmth}打底")
            else:
                parts.append(f"{warmth}{CATEGORY_LABELS.get(category, category)}")

    head = f"体感 {facts.feels_min:.1f}–{facts.feels_max:.1f}℃，"
    body = " + ".join(parts) if parts else "无可用单品"
    tail = ""
    if want_extra:
        tail = "；早晚温差大，加了一层打底"
    elif want_outer:
        tail = "；早上偏凉，配了外套"
    return f"{head}{body}{tail}"


def _score(items: list[RuleItem], target_warmth: int, target_formality: int) -> tuple[int, int, tuple[int, ...]]:
    warmth_cost = 0
    formality_cost = 0
    for item in items:
        w_cost, f_cost, _ = _item_key(item, target_warmth, target_formality)
        warmth_cost += w_cost
        formality_cost += f_cost
    return (warmth_cost, formality_cost, tuple(sorted(item.id for item in items)))


def build_outfits(
    facts: WeatherFacts,
    items: list[RuleItem],
    occasion: str | None = None,
    negative: set[str] | None = None,
) -> RecommendPlan:
    # 用户明确说不要的品类：从候选里剔掉，并且不再强制要求（否则校验必挂）
    excluded = negative or set()
    if excluded:
        items = [item for item in items if item.category not in excluded]

    target_warmth = need_warmth(facts.feels_min)
    want_outer = need_outer(facts.feels_min) and "outer" not in excluded
    want_extra = need_extra(facts.feels_min, facts.feels_max)
    target_formality = formality_of(occasion)

    def assemble(
        pool: list[RuleItem], relaxed: bool
    ) -> tuple[tuple[OutfitPlan, ...], list[str]]:
        tops = _rank([i for i in pool if i.category == "top"], target_warmth, target_formality)
        bottoms = _rank([i for i in pool if i.category == "bottom"], target_warmth, target_formality)
        shoes = _rank([i for i in pool if i.category == "shoes"], target_warmth, target_formality)
        outers = _rank([i for i in pool if i.category == "outer"], target_warmth, target_formality)
        dresses = _rank([i for i in pool if i.category == "dress"], target_warmth, target_formality)
        accessories = _rank(
            [i for i in pool if i.category == "accessory"], target_warmth, target_formality
        )

        missing: list[str] = []
        if not tops and not dresses:
            missing.append("上衣或连衣裙")
        if not bottoms and not dresses:
            missing.append("下装")
        if not shoes:
            missing.append("鞋")
        if want_outer and not outers:
            missing.append("外套")

        # 候选组合：基础三件套 + 连衣裙替代方案
        # combo 用来保证「三套之间下装/鞋不重样」，凑不满时允许回退重复。
        candidates: list[tuple[list[RuleItem], tuple[object, ...]]] = []
        if tops and bottoms and shoes:
            for top in tops[:4]:
                for bottom in bottoms[:4]:
                    for shoe in shoes[:4]:
                        candidates.append(([top, bottom, shoe], ("bottom", bottom.id, shoe.id)))
        if dresses and shoes:
            for dress in dresses[:4]:
                for shoe in shoes[:4]:
                    candidates.append(([dress, shoe], ("dress", dress.id, shoe.id)))

        decorated: list[tuple[tuple, tuple[object, ...], list[RuleItem]]] = []
        seen: set[frozenset[int]] = set()
        for base, combo in candidates:
            outfit = _decorate(
                base,
                tops=tops,
                outers=outers,
                accessories=accessories,
                want_outer=want_outer,
                want_extra=want_extra,
                target_warmth=target_warmth,
            )
            ids = frozenset(item.id for item in outfit)
            if len(ids) != len(outfit):
                continue  # 同一套里不许重复
            if ids in seen:
                continue
            seen.add(ids)
            decorated.append((_score(outfit, target_warmth, target_formality), combo, outfit))

        decorated.sort(key=lambda entry: entry[0])

        # 先按 (下装, 鞋) 组合去重地取，凑不满 3 套才允许重复组合。
        picked: list[list[RuleItem]] = []
        used_combos: set[tuple[object, ...]] = set()
        leftovers: list[list[RuleItem]] = []
        for _score_value, combo, outfit in decorated:
            if combo in used_combos:
                leftovers.append(outfit)
                continue
            used_combos.add(combo)
            picked.append(outfit)
            if len(picked) == MAX_OUTFITS:
                break

        if len(picked) < MAX_OUTFITS:
            for outfit in leftovers:
                picked.append(outfit)
                if len(picked) == MAX_OUTFITS:
                    break

        outfits = tuple(
            OutfitPlan(
                items=tuple(outfit),
                reason=_reason(facts, outfit, want_outer=want_outer, want_extra=want_extra),
                relaxed_occasion=relaxed,
            )
            for outfit in picked
        )
        return outfits, missing

    # 严格按场合过滤：目标场合 + 无场合（通用）的单品
    strict_pool = [item for item in items if _usable(item, occasion)]
    outfits, missing = assemble(strict_pool, relaxed=False)
    if outfits:
        return RecommendPlan(outfits=outfits, notice=_notice(missing, len(outfits)))

    # 兜底：指定了场合却组不出 ≥1 套时，放宽到全量（不按场合过滤）再试一次。
    # 只放宽场合，品类与厚薄约束不变；组出的套标记 relaxed_occasion，notice 如实说明。
    if occasion:
        relaxed_outfits, relaxed_missing = assemble(items, relaxed=True)
        if relaxed_outfits:
            return RecommendPlan(outfits=relaxed_outfits, notice=_relaxed_notice(occasion))
        return RecommendPlan(outfits=(), notice=_notice(relaxed_missing, 0))

    return RecommendPlan(outfits=(), notice=_notice(missing, 0))


def _notice(missing: list[str], count: int) -> str | None:
    if not missing:
        if count == 0:
            return "当前衣橱组不出完整搭配，先补上衣、下装和鞋"
        return None

    joined = "、".join(missing)
    if count == 0:
        return f"衣橱里没有{joined}，暂时组不出搭配"
    if count < MAX_OUTFITS:
        return f"衣橱里没有{joined}，只能组出 {count} 套"
    return f"衣橱里没有{joined}，搭配可能不完整"


def _relaxed_notice(occasion: str) -> str:
    """场合不足兜底时的诚实说明：不假装这些都是专门为该场合的。"""
    label = OCCASION_LABELS.get(occasion, occasion)
    return f"专门为{label}场合的衣服不够，这几套里有些不是专门为{label}的，你看着挑"
