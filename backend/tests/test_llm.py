"""N4 测试：LLM 适配层 + 候选池校验 + 降级。全程 mock httpx，不打网络。"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from sqlalchemy import delete

from app import limits, llm, llm_cache, llm_pick, weather
from app.db import SessionLocal
from app.models import WeatherSnapshotRow
from app.llm import LLMConfig, LLMError, chat_json, key_fingerprint, resolve_llm_config
from app.llm_pick import PickResult, build_pool, validate_selection
from app.rules import RuleItem, WeatherFacts

CONFIG = LLMConfig(base_url="https://api.deepseek.com", model="deepseek-chat", api_key="sk-test-secret")

WEATHER_DAILY = {
    "time": ["2026-11-21"],
    "temperature_2m_max_cma_grapes_global": [14.6],
    "temperature_2m_min_cma_grapes_global": [6.8],
    "apparent_temperature_max_cma_grapes_global": [11.9],
    "apparent_temperature_min_cma_grapes_global": [4.1],
    "precipitation_probability_max_cma_grapes_global": [None],
    "wind_speed_10m_max_cma_grapes_global": [9.7],
    "uv_index_max_cma_grapes_global": [None],
    "weather_code_cma_grapes_global": [0],
    "temperature_2m_max_best_match": [15.5],
    "temperature_2m_min_best_match": [3.1],
    "apparent_temperature_max_best_match": [13.2],
    "apparent_temperature_min_best_match": [0.8],
    "precipitation_probability_max_best_match": [0],
    "wind_speed_10m_max_best_match": [6.5],
    "uv_index_max_best_match": [4.45],
    "weather_code_best_match": [0],
}


class FakeResponse:
    def __init__(self, payload: dict | None = None, status_code: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeClient:
    """同一个 client 同时服务天气 GET 和模型 POST。"""

    chat_queue: list[object] = []
    chat_calls = 0
    weather_calls = 0
    weather_override: dict | None = None
    last_headers: dict | None = None
    last_payload: dict | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url, params=None):
        FakeClient.weather_calls += 1
        return FakeResponse(FakeClient.weather_override or {"daily": WEATHER_DAILY})

    async def post(self, url, json=None, headers=None):
        FakeClient.chat_calls += 1
        FakeClient.last_headers = headers
        FakeClient.last_payload = json
        item = FakeClient.chat_queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def reply(content: dict | str, finish_reason: str = "stop") -> FakeResponse:
    text = content if isinstance(content, str) else json.dumps(content)
    return FakeResponse(
        {
            "choices": [{"message": {"content": text}, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": 82, "completion_tokens": 15},
        }
    )


def reply_raw(message: dict, finish_reason: str | None = "stop") -> FakeResponse:
    choice: dict = {"message": message}
    if finish_reason is not None:
        choice["finish_reason"] = finish_reason
    return FakeResponse({"choices": [choice]})


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    FakeClient.chat_queue = []
    FakeClient.chat_calls = 0
    FakeClient.weather_calls = 0
    FakeClient.weather_override = None
    FakeClient.last_headers = None
    FakeClient.last_payload = None
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.delenv("EW_LLM_KEY", raising=False)
    monkeypatch.delenv("EW_LLM_CACHE_TTL", raising=False)
    monkeypatch.delenv("EW_LLM_RATE_LIMIT_PER_MIN", raising=False)
    llm_cache.clear()
    limits.clear()
    weather.clear_cache()
    with SessionLocal() as db:
        db.execute(delete(WeatherSnapshotRow))
        db.commit()
    yield FakeClient


def wardrobe() -> list[RuleItem]:
    return [
        RuleItem(1, "top", 2, "casual"),
        RuleItem(2, "top", 1, "casual"),
        RuleItem(10, "bottom", 2, "casual"),
        RuleItem(11, "bottom", 3, "casual"),
        RuleItem(20, "shoes", 2, "casual"),
        RuleItem(30, "outer", 3, "casual"),
        RuleItem(40, "accessory", 1, "casual"),
    ]


def facts(feels_min: float = 4.1, feels_max: float = 11.9) -> WeatherFacts:
    return WeatherFacts(date="2026-11-21", feels_min=feels_min, feels_max=feels_max)


# --- 配置解析 -------------------------------------------------------------


def test_resolve_config_header_wins(monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "env-key")
    config = resolve_llm_config("header-key")
    assert config is not None and config.api_key == "header-key"


def test_resolve_config_env_fallback(monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "env-key")
    config = resolve_llm_config(None)
    assert config is not None and config.api_key == "env-key"


def test_resolve_config_none_without_key():
    assert resolve_llm_config(None) is None
    assert resolve_llm_config("   ") is None


def test_key_fingerprint_is_short_and_not_plaintext():
    fingerprint = key_fingerprint("sk-test-secret")
    assert len(fingerprint) == 8
    assert "sk-test-secret" not in fingerprint


def test_defaults_are_chat_without_v1(monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "k")
    config = resolve_llm_config(None)
    assert config is not None
    assert config.model == "deepseek-chat"
    assert config.base_url == "https://api.deepseek.com"
    assert config.max_tokens == 800


def test_model_and_max_tokens_are_configurable(monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "k")
    monkeypatch.setenv("EW_LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("EW_LLM_MAX_TOKENS", "1200")
    config = resolve_llm_config(None)
    assert config is not None
    assert config.model == "deepseek-v4-pro"
    assert config.max_tokens == 1200


# --- chat_json 的错误折码 --------------------------------------------------


@pytest.mark.anyio
async def test_chat_json_payload_shape():
    FakeClient.chat_queue = [reply({"item_ids": [1]})]
    await chat_json(CONFIG, "s", "u")
    payload = FakeClient.last_payload
    assert payload["model"] == "deepseek-chat"
    assert payload["max_tokens"] == 800
    assert payload["temperature"] == 0
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["role"] == "system"


@pytest.mark.anyio
async def test_chat_json_ignores_reasoning_content():
    FakeClient.chat_queue = [
        reply_raw(
            {
                "content": '{"item_ids": [1, 2, 3]}',
                "reasoning_content": "先看看天气……（不解析这段）",
            }
        )
    ]
    data, usage = await chat_json(CONFIG, "s", "u")
    assert data == {"item_ids": [1, 2, 3]}
    assert usage == {"prompt_tokens": None, "completion_tokens": None}


@pytest.mark.anyio
async def test_chat_json_truncated_with_empty_content():
    """reasoning tokens 吃掉预算：content 空 + finish_reason=length → truncated。"""
    FakeClient.chat_queue = [reply_raw({"content": ""}, finish_reason="length")]
    with pytest.raises(LLMError) as info:
        await chat_json(CONFIG, "s", "u")
    assert info.value.reason == "truncated"


@pytest.mark.anyio
async def test_chat_json_empty_content_without_length_still_truncated():
    FakeClient.chat_queue = [reply_raw({"content": "   "})]
    with pytest.raises(LLMError) as info:
        await chat_json(CONFIG, "s", "u")
    assert info.value.reason == "truncated"


@pytest.mark.anyio
async def test_chat_json_ok():
    FakeClient.chat_queue = [reply({"item_ids": [1]})]
    data, usage = await chat_json(CONFIG, "sys", "user")
    assert data == {"item_ids": [1]}
    assert usage == {"prompt_tokens": 82, "completion_tokens": 15}
    assert FakeClient.last_headers["Authorization"] == "Bearer sk-test-secret"


@pytest.mark.anyio
async def test_chat_json_usage_missing_is_none_not_zero():
    """上游没给 usage 时记 None，不要伪造 0。"""
    FakeClient.chat_queue = [FakeResponse({"choices": [{"message": {"content": '{"ok": 1}'}}]})]
    data, usage = await chat_json(CONFIG, "s", "u")
    assert data == {"ok": 1}
    assert usage == {"prompt_tokens": None, "completion_tokens": None}


@pytest.mark.anyio
async def test_chat_json_strips_code_fence():
    FakeClient.chat_queue = [reply('```json\n{"item_ids": [1, 2, 3]}\n```')]
    data, _usage = await chat_json(CONFIG, "s", "u")
    assert data == {"item_ids": [1, 2, 3]}


@pytest.mark.anyio
async def test_chat_json_429_raises_rate_limited():
    FakeClient.chat_queue = [FakeResponse(status_code=429)]
    with pytest.raises(LLMError) as info:
        await chat_json(CONFIG, "s", "u")
    assert info.value.reason == "rate_limited"


@pytest.mark.anyio
async def test_chat_json_500_raises_upstream():
    FakeClient.chat_queue = [FakeResponse(status_code=503)]
    with pytest.raises(LLMError) as info:
        await chat_json(CONFIG, "s", "u")
    assert info.value.reason == "upstream_503"


@pytest.mark.anyio
async def test_chat_json_timeout():
    FakeClient.chat_queue = [httpx.ConnectTimeout("boom")]
    with pytest.raises(LLMError) as info:
        await chat_json(CONFIG, "s", "u")
    assert info.value.reason == "timeout"


@pytest.mark.anyio
async def test_chat_json_non_json_content():
    FakeClient.chat_queue = [reply("这不是 JSON")]
    with pytest.raises(LLMError) as info:
        await chat_json(CONFIG, "s", "u")
    assert info.value.reason == "bad_json"


# --- 候选池与校验 ----------------------------------------------------------


def test_pool_sizes_and_outer_rule():
    pool = build_pool(facts(), wardrobe(), "casual")
    by_cat: dict[str, int] = {}
    for item in pool:
        by_cat[item.category] = by_cat.get(item.category, 0) + 1
    assert by_cat["top"] == 2  # 衣橱只有 2 件
    assert by_cat["bottom"] == 2
    assert by_cat["shoes"] == 1
    assert by_cat["outer"] == 1
    assert 3 <= len(pool) <= 15


def test_pool_drops_outer_when_warm():
    pool = build_pool(facts(25, 30), wardrobe(), "casual")
    assert all(item.category != "outer" for item in pool)


def test_pool_includes_dress():
    items = wardrobe() + [RuleItem(50, "dress", 2, "formal"), RuleItem(51, "dress", 1, "formal")]
    pool = build_pool(facts(), items, "formal")
    dresses = [item for item in pool if item.category == "dress"]
    assert len(dresses) == 2


@pytest.mark.anyio
async def test_dress_only_wardrobe_still_calls_model():
    """只有连衣裙 + 鞋（没有 top/bottom）：不该被 missing_category 挡掉。"""
    items = [RuleItem(50, "dress", 1, "casual"), RuleItem(20, "shoes", 1, "casual")]
    FakeClient.chat_queue = [
        reply({"item_ids": [50, 20]}),
        reply({"item_ids": [50, 20]}),
    ]

    result = await llm_pick.pick_with_llm(CONFIG, facts(25, 30), items, "casual")

    assert FakeClient.chat_calls >= 1, "模型应该被调用，而不是直接降级"
    assert result.fallback_reason != "missing_category"


@pytest.mark.anyio
async def test_formal_wardrobe_without_bottom_reaches_model():
    """formal 形态：bottom=0、dress=2 —— 之前这里会 missing_category 直接跳过模型。"""
    items = [
        RuleItem(1, "top", 2, "formal"),
        RuleItem(2, "top", 3, "formal"),
        RuleItem(30, "outer", 3, "formal"),
        RuleItem(20, "shoes", 2, "formal"),
        RuleItem(50, "dress", 2, "formal"),
        RuleItem(51, "dress", 2, "formal"),
    ]
    FakeClient.chat_queue = [
        reply({"item_ids": [50, 20, 30], "reason": "formal 裙装"}),
    ]

    result = await llm_pick.pick_with_llm(CONFIG, facts(), items, "formal")

    assert FakeClient.chat_calls == 1
    assert result.fallback_reason != "missing_category"
    assert result.source == "llm"
    assert [item.id for item in result.outfit] == [50, 20, 30]


def test_validate_accepts_complete_outfit():
    pool = build_pool(facts(), wardrobe(), "casual")
    chosen, problems = validate_selection({"item_ids": [1, 10, 20, 30]}, pool, True)
    assert chosen is not None and problems == []
    assert {i.category for i in chosen} == {"top", "bottom", "shoes", "outer"}


@pytest.mark.parametrize(
    ("ids", "hint"),
    [
        ([1, 1, 10, 20], "重复"),
        ([1, 10], "件数"),
        ([1, 2, 10, 11, 20, 30, 40, 1], "件数"),
    ],
)
def test_validate_rejects_bad_shapes(ids, hint):
    pool = build_pool(facts(), wardrobe(), "casual")
    chosen, problems = validate_selection({"item_ids": ids}, pool, True)
    assert chosen is None
    assert any(hint in problem for problem in problems), problems


def test_validate_rejects_unknown_id():
    pool = build_pool(facts(), wardrobe(), "casual")
    chosen, problems = validate_selection({"item_ids": [1, 10, 20, 999]}, pool, False)
    assert chosen is None
    assert any("候选池" in problem for problem in problems)


def test_validate_requires_bottom():
    pool = build_pool(facts(), wardrobe(), "casual")
    chosen, problems = validate_selection({"item_ids": [1, 20, 30]}, pool, True)
    assert chosen is None
    assert any("下装" in problem for problem in problems)


def test_validate_requires_outer_when_cold():
    pool = build_pool(facts(), wardrobe(), "casual")
    chosen, problems = validate_selection({"item_ids": [1, 10, 20]}, pool, True)
    assert chosen is None
    assert any("外套" in problem for problem in problems)


def test_validate_rejects_non_int_ids():
    pool = build_pool(facts(), wardrobe(), "casual")
    chosen, problems = validate_selection({"item_ids": ["1", 10, 20]}, pool, False)
    assert chosen is None


# --- 完整 pick 流程 --------------------------------------------------------


@pytest.mark.anyio
async def test_pick_success_first_try():
    FakeClient.chat_queue = [reply({"item_ids": [1, 10, 20, 30], "reason": "体感偏凉，加了外套"})]
    result = await llm_pick.pick_with_llm(CONFIG, facts(), wardrobe(), "casual")
    assert isinstance(result, PickResult)
    assert result.source == "llm"
    assert result.attempts == 1
    assert result.reason == "体感偏凉，加了外套"
    assert [i.id for i in result.outfit] == [1, 10, 20, 30]
    assert FakeClient.chat_calls == 1


@pytest.mark.anyio
async def test_pick_repairs_after_hallucination():
    FakeClient.chat_queue = [
        reply({"item_ids": [999, 10, 20, 30]}),
        reply({"item_ids": [1, 10, 20, 30], "reason": "第二次对了"}),
    ]
    result = await llm_pick.pick_with_llm(CONFIG, facts(), wardrobe(), "casual")
    assert result.source == "llm"
    assert result.attempts == 2
    assert result.reason == "第二次对了"
    assert "候选池" in FakeClient.last_payload["messages"][1]["content"]


@pytest.mark.anyio
async def test_pick_falls_back_after_two_failures():
    FakeClient.chat_queue = [
        reply({"item_ids": [999, 10, 20, 30]}),
        reply({"item_ids": [999, 1, 2, 3]}),
    ]
    result = await llm_pick.pick_with_llm(CONFIG, facts(), wardrobe(), "casual")
    assert result.source == "rules"
    assert result.attempts == 2
    assert result.fallback_reason == "invalid_ids"
    assert result.outfit  # 规则结果有人接住


@pytest.mark.anyio
async def test_pick_falls_back_on_rate_limit():
    FakeClient.chat_queue = [FakeResponse(status_code=429)]
    result = await llm_pick.pick_with_llm(CONFIG, facts(), wardrobe(), "casual")
    assert result.source == "rules"
    assert result.fallback_reason == "rate_limited"


@pytest.mark.anyio
async def test_pick_falls_back_on_timeout():
    FakeClient.chat_queue = [httpx.ConnectTimeout("boom")]
    result = await llm_pick.pick_with_llm(CONFIG, facts(), wardrobe(), "casual")
    assert result.fallback_reason == "timeout"


# --- 接口层 ---------------------------------------------------------------


def _ensure_wardrobe(client) -> dict:
    """保证四类基础件各有一件「场合为空」的单品（任何场合都可用），
    这样后续请求不会因为补数据而改变 wardrobe_hash。"""
    items = client.get("/api/items", params={"limit": 500}).json()["items"]
    neutral = {item["category"] for item in items if not item["occasion"]}
    for category in ("top", "bottom", "shoes", "outer"):
        if category not in neutral:
            client.post("/api/items", json={"category": category})
    return client.get("/api/recommend", params={"mode": "rules"}).json()


def test_endpoint_mode_rules_never_calls_llm(client):
    _ensure_wardrobe(client)
    res = client.get("/api/recommend", params={"mode": "rules"})
    body = res.json()
    assert body["source"] == "rules"
    assert body["attempts"] == 0
    assert body["fallback_reason"] is None
    assert FakeClient.chat_calls == 0


def test_endpoint_without_key_falls_back_without_calling_upstream(client):
    _ensure_wardrobe(client)
    res = client.get("/api/recommend", params={"mode": "llm"})
    body = res.json()
    assert res.status_code == 200
    assert body["source"] == "rules"
    assert body["fallback_reason"] == "no_key"
    assert FakeClient.chat_calls == 0


def test_endpoint_llm_replaces_first_outfit(client):
    baseline = _ensure_wardrobe(client)
    ids = [item["id"] for item in baseline["outfits"][0]["items"]]
    FakeClient.chat_queue = [reply({"item_ids": ids, "reason": "模型选的这套"})]

    res = client.get("/api/recommend", params={"mode": "llm"}, headers={"X-LLM-Key": "sk-test-secret"})
    body = res.json()
    assert res.status_code == 200
    assert body["source"] == "llm"
    assert body["attempts"] == 1
    assert body["fallback_reason"] is None
    assert body["outfits"][0]["reason"] == "模型选的这套"
    assert [item["id"] for item in body["outfits"][0]["items"]] == ids


def test_endpoint_llm_failure_keeps_three_rule_outfits(client):
    baseline = _ensure_wardrobe(client)
    FakeClient.chat_queue = [
        reply({"item_ids": [987654, 1, 2, 3]}),
        reply({"item_ids": [987654, 4, 5, 6]}),
    ]

    res = client.get("/api/recommend", params={"mode": "llm"}, headers={"X-LLM-Key": "sk-test-secret"})
    body = res.json()
    assert res.status_code == 200
    assert body["source"] == "rules"
    assert body["fallback_reason"] in {"invalid_ids", "invalid_outfit"}
    assert body["outfits"] == baseline["outfits"]


def test_endpoint_truncated_falls_back_to_rules(client):
    """真实会发生的场景：预算被 reasoning 吃掉，content 空 + finish_reason=length。"""
    baseline = _ensure_wardrobe(client)
    FakeClient.chat_queue = [
        reply_raw({"content": ""}, finish_reason="length"),
        reply_raw({"content": ""}, finish_reason="length"),
    ]

    res = client.get(
        "/api/recommend", params={"mode": "llm"}, headers={"X-LLM-Key": "sk-test-secret"}
    )
    body = res.json()
    assert res.status_code == 200
    assert body["source"] == "rules"
    assert body["fallback_reason"] == "truncated"
    assert body["attempts"] == 1  # 第一次就失败了，没重试（LLMError 直接降级）
    assert body["outfits"] == baseline["outfits"]


def test_logs_do_not_contain_plaintext_key(client, caplog):
    _ensure_wardrobe(client)
    baseline = client.get("/api/recommend", params={"mode": "rules"}).json()
    ids = [item["id"] for item in baseline["outfits"][0]["items"]]
    FakeClient.chat_queue = [reply({"item_ids": ids, "reason": "ok"})]

    with caplog.at_level(logging.INFO):
        client.get("/api/recommend", params={"mode": "llm"}, headers={"X-LLM-Key": "sk-very-secret-key"})

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "sk-very-secret-key" not in text
    assert "llm_pick" in text
    assert key_fingerprint("sk-very-secret-key") in text


# --- N5：缓存与限流 -------------------------------------------------------

HEADERS = {"X-LLM-Key": "sk-test-secret"}


def _valid_reply(client, occasion: str = "casual") -> FakeResponse:
    _ensure_wardrobe(client)
    baseline = client.get(
        "/api/recommend", params={"mode": "rules", "occasion": occasion}
    ).json()
    ids = [item["id"] for item in baseline["outfits"][0]["items"]]
    return reply({"item_ids": ids, "reason": f"模型选的 {occasion}"})


def test_cache_hit_second_request_does_not_call_upstream(client):
    _ensure_wardrobe(client)
    FakeClient.chat_queue = [_valid_reply(client)]

    first = client.get(
        "/api/recommend", params={"mode": "llm"}, headers=HEADERS
    ).json()
    second = client.get(
        "/api/recommend", params={"mode": "llm"}, headers=HEADERS
    ).json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert FakeClient.chat_calls == 1
    assert second["source"] == "llm"
    assert second["outfits"][0]["reason"] == first["outfits"][0]["reason"]


def test_cache_invalidated_when_item_changes(client):
    import time as time_module

    _ensure_wardrobe(client)
    FakeClient.chat_queue = [_valid_reply(client)]
    client.get("/api/recommend", params={"mode": "llm"}, headers=HEADERS)

    items = client.get("/api/items", params={"limit": 1}).json()["items"]
    target = items[0]
    time_module.sleep(1.05)  # updated_at 是秒级精度，保证真的变了
    client.patch(f"/api/items/{target['id']}", json={"color_family": "藏青"})

    FakeClient.chat_queue = [_valid_reply(client)]
    second = client.get(
        "/api/recommend", params={"mode": "llm"}, headers=HEADERS
    ).json()

    assert second["cached"] is False
    assert FakeClient.chat_calls == 2


def test_cache_is_keyed_by_occasion(client):
    _ensure_wardrobe(client)
    FakeClient.chat_queue = [_valid_reply(client, "casual")]
    client.get("/api/recommend", params={"mode": "llm", "occasion": "casual"}, headers=HEADERS)

    FakeClient.chat_queue = [_valid_reply(client, "work")]
    client.get("/api/recommend", params={"mode": "llm", "occasion": "work"}, headers=HEADERS)

    # 回到 casual：应该命中第一次的缓存
    third = client.get(
        "/api/recommend", params={"mode": "llm", "occasion": "casual"}, headers=HEADERS
    ).json()

    assert FakeClient.chat_calls == 2
    assert third["cached"] is True


def test_cache_is_keyed_by_weather(client):
    _ensure_wardrobe(client)
    FakeClient.chat_queue = [_valid_reply(client)]
    client.get("/api/recommend", params={"mode": "llm"}, headers=HEADERS)

    # 换一份天气（体感不同 → weather_hash 变）。
    # 天气服务自己有 2 小时快照缓存，这里要清掉才会真的重新取数
    weather.clear_cache()
    FakeClient.weather_override = {
        "daily": {
            **WEATHER_DAILY,
            "apparent_temperature_min_cma_grapes_global": [1.0],
            "apparent_temperature_max_cma_grapes_global": [8.0],
        }
    }
    FakeClient.chat_queue = [_valid_reply(client)]
    second = client.get(
        "/api/recommend", params={"mode": "llm"}, headers=HEADERS
    ).json()

    assert second["cached"] is False
    assert FakeClient.chat_calls == 2


def test_fallback_result_is_not_cached(client):
    _ensure_wardrobe(client)
    FakeClient.chat_queue = [FakeResponse(status_code=429)]

    first = client.get(
        "/api/recommend", params={"mode": "llm"}, headers=HEADERS
    ).json()
    assert first["source"] == "rules"
    assert first["fallback_reason"] == "rate_limited"

    FakeClient.chat_queue = [_valid_reply(client)]
    second = client.get(
        "/api/recommend", params={"mode": "llm"}, headers=HEADERS
    ).json()

    assert second["cached"] is False
    assert FakeClient.chat_calls == 2
    assert second["source"] == "llm"


def test_rate_limit_falls_back_to_rules_with_200(client, monkeypatch):
    monkeypatch.setenv("EW_LLM_RATE_LIMIT_PER_MIN", "2")
    _ensure_wardrobe(client)

    FakeClient.chat_queue = [_valid_reply(client, "casual")]
    client.get("/api/recommend", params={"mode": "llm", "occasion": "casual"}, headers=HEADERS)

    FakeClient.chat_queue = [_valid_reply(client, "work")]
    client.get("/api/recommend", params={"mode": "llm", "occasion": "work"}, headers=HEADERS)

    FakeClient.chat_queue = [_valid_reply(client, "sport")]
    res = client.get(
        "/api/recommend", params={"mode": "llm", "occasion": "sport"}, headers=HEADERS
    )
    body = res.json()

    assert res.status_code == 200
    assert body["source"] == "rules"
    assert body["fallback_reason"] == "rate_limited"
    assert "规则推荐" in (body["notice"] or "")
    assert res.headers["X-RateLimit-Remaining"] == "0"
    assert FakeClient.chat_calls == 2  # 第三次没有打上游


def test_cache_hit_does_not_consume_quota(client, monkeypatch):
    monkeypatch.setenv("EW_LLM_RATE_LIMIT_PER_MIN", "2")
    _ensure_wardrobe(client)

    FakeClient.chat_queue = [_valid_reply(client, "casual")]
    first = client.get(
        "/api/recommend", params={"mode": "llm", "occasion": "casual"}, headers=HEADERS
    ).json()
    assert first["cached"] is False

    # 第二次命中缓存，不消耗额度
    hit = client.get(
        "/api/recommend", params={"mode": "llm", "occasion": "casual"}, headers=HEADERS
    ).json()
    assert hit["cached"] is True

    # 额度还剩 1 次：work 应该放行
    FakeClient.chat_queue = [_valid_reply(client, "work")]
    work = client.get(
        "/api/recommend", params={"mode": "llm", "occasion": "work"}, headers=HEADERS
    ).json()
    assert work["source"] == "llm"
    assert work["fallback_reason"] is None

    # 第三次真实调用被限流
    FakeClient.chat_queue = [_valid_reply(client, "sport")]
    sport = client.get(
        "/api/recommend", params={"mode": "llm", "occasion": "sport"}, headers=HEADERS
    ).json()
    assert sport["fallback_reason"] == "rate_limited"


def test_rules_mode_never_touches_cache_or_limiter(client):
    _ensure_wardrobe(client)
    body = client.get("/api/recommend", params={"mode": "rules"}).json()
    assert body["cached"] is False
    assert FakeClient.chat_calls == 0
    assert llm_cache.size() == 0
