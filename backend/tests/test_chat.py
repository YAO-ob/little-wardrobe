"""W6b：对话入口（意图 + 工具链）。天气与模型上游全部 mock。"""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import delete

from app import limits, llm_cache, weather
from app.db import SessionLocal
from app.models import Item, WeatherSnapshotRow

WEATHER_DAILY = {
    "time": ["2026-11-22"],
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
    def __init__(self, payload: dict | None = None, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeClient:
    chat_queue: list = []
    chat_calls = 0
    weather_calls = 0
    last_messages: list | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        FakeClient.weather_calls += 1
        return FakeResponse({"daily": WEATHER_DAILY})

    async def post(self, url, json=None, headers=None):
        FakeClient.chat_calls += 1
        FakeClient.last_messages = json.get("messages") if json else None
        item = FakeClient.chat_queue.pop(0) if FakeClient.chat_queue else {}
        if isinstance(item, Exception):
            raise item
        content = json_module.dumps(item)
        return FakeResponse(
            {
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 10},
            }
        )


json_module = json


@pytest.fixture(autouse=True)
def fake_upstream(monkeypatch):
    FakeClient.chat_queue = []
    FakeClient.chat_calls = 0
    FakeClient.weather_calls = 0
    FakeClient.last_messages = None
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.delenv("EW_LLM_KEY", raising=False)
    llm_cache.clear()
    limits.clear()
    weather.clear_cache()
    weather.clear_cooldown()
    with SessionLocal() as db:
        db.execute(delete(WeatherSnapshotRow))
        # 每个用例从空衣橱开始，避免别的用例留下的单品把候选池挤满
        db.execute(delete(Item))
        db.commit()
    yield FakeClient


@pytest.fixture
def wardrobe(client):
    """每类两件、场合不限，保证 exclude 之后仍能组套。"""
    ids: list[int] = []
    for category in ("top", "top", "bottom", "bottom", "shoes", "shoes", "outer", "outer"):
        res = client.post("/api/items", json={"category": category, "warmth": 2})
        ids.append(res.json()["id"])
    return ids


def chat(client, message: str, **kwargs) -> dict:
    res = client.post("/api/chat", json={"message": message, **kwargs})
    assert res.status_code == 200, res.text
    return res.json()


def test_recommend_intent_from_casual_sentence(client, wardrobe):
    body = chat(client, "我晚点要约会")

    assert body["intent"] == "recommend"
    assert body["occasion"] == "casual"
    assert [step["tool"] for step in body["trace"]] == [
        "get_weather",
        "search_wardrobe",
        "build_outfits",
        "validate",
    ]
    assert body["outfits"]
    assert "约会" in body["reply"]


def test_work_sentence_maps_to_work(client, wardrobe):
    body = chat(client, "上班穿什么")
    assert body["occasion"] == "work"
    assert "上班" in body["reply"]


def test_reroll_excludes_current_outfit(client, wardrobe):
    first = chat(client, "我晚点要约会")
    excluded = [item["id"] for item in first["outfits"][0]["items"]]

    body = chat(client, "换一套", exclude_ids=excluded)

    assert body["intent"] == "reroll"
    assert body["outfits"]
    returned = {item["id"] for outfit in body["outfits"] for item in outfit["items"]}
    assert returned.isdisjoint(excluded)
    assert body["reply"].startswith("换一套")


def test_weather_intent_has_single_step_and_no_outfits(client, wardrobe):
    body = chat(client, "今天天气怎么样")

    assert body["intent"] == "weather"
    assert len(body["trace"]) == 1
    assert body["trace"][0]["tool"] == "get_weather"
    assert body["outfits"] == []
    assert "体感" in body["reply"]


def test_without_key_still_works_for_complex_sentence(client, wardrobe):
    body = chat(client, "帮我看看穿什么好")
    assert body["intent"] == "recommend"
    assert body["occasion"] is None
    assert body["outfits"]
    assert FakeClient.chat_calls == 0


def test_invalid_llm_occasion_is_discarded(client, wardrobe, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    FakeClient.chat_queue = [
        {"reply": "随便穿", "intent": "recommend", "occasion": "party", "item_ids": []}
    ]

    body = chat(client, "帮我看看穿什么好")

    assert FakeClient.chat_calls == 1
    assert body["occasion"] is None  # 越界整条丢弃，保留规则结果
    assert body["intent"] == "recommend"
    assert body["fallback_reason"] == "invalid_intent"
    assert body["source"] == "rules"


def test_empty_and_overlong_message_are_422(client):
    assert client.post("/api/chat", json={"message": "   "}).status_code == 422
    assert client.post("/api/chat", json={"message": "长" * 201}).status_code == 422


def test_chat_intent_reply_comes_from_model(client, wardrobe, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    FakeClient.chat_queue = [
        {"reply": "累就先别折腾了，抓件舒服的就行。", "intent": "chat", "occasion": None, "item_ids": []}
    ]

    body = chat(client, "你好，今天好累")

    assert body["intent"] == "chat"
    assert body["outfits"] == []
    assert body["reply"] == "累就先别折腾了，抓件舒服的就行。"
    assert body["source"] == "llm"
    assert [step["tool"] for step in body["trace"]][-1] == "model"


def test_recommend_intent_uses_ids_from_pool(client, wardrobe, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    top, bottom, shoes, outer = wardrobe[0], wardrobe[2], wardrobe[4], wardrobe[6]
    FakeClient.chat_queue = [
        {
            "reply": "约会就松快一点。",
            "intent": "recommend",
            "occasion": "casual",
            "item_ids": [top, bottom, shoes, outer],
        }
    ]

    body = chat(client, "我想穿休闲点去约会")

    assert body["intent"] == "recommend"
    assert body["reply"] == "约会就松快一点。"
    assert body["source"] == "llm"
    picked = {item["id"] for item in body["outfits"][0]["items"]}
    assert picked == {top, bottom, shoes, outer}


def test_out_of_pool_ids_are_repaired(client, wardrobe, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    top, bottom, shoes, outer = wardrobe[0], wardrobe[2], wardrobe[4], wardrobe[6]
    FakeClient.chat_queue = [
        {"reply": "先这样", "intent": "recommend", "occasion": "casual", "item_ids": [99999]},
        {
            "reply": "先这样",
            "intent": "recommend",
            "occasion": "casual",
            "item_ids": [top, bottom, shoes, outer],
        },
    ]

    body = chat(client, "我想穿休闲点去约会")

    assert FakeClient.chat_calls == 2
    assert body["source"] == "llm"
    assert {item["id"] for item in body["outfits"][0]["items"]} == {top, bottom, shoes, outer}


def test_failed_repair_keeps_model_reply(client, wardrobe, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    FakeClient.chat_queue = [
        {"reply": "我尽量挑挑。", "intent": "recommend", "occasion": "casual", "item_ids": [1]},
        {"reply": "我还是没挑好。", "intent": "recommend", "occasion": "casual", "item_ids": [2]},
    ]

    body = chat(client, "我想穿休闲点去约会")

    assert body["source"] == "rules"
    assert body["fallback_reason"] == "invalid_ids"
    assert body["reply"]  # 模型写的回复保留，不是模板
    assert body["outfits"]  # 规则结果顶上


def test_weather_intent_ignores_item_ids(client, wardrobe, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    FakeClient.chat_queue = [
        {"reply": "今天有点冷，加件外套。", "intent": "weather", "occasion": None, "item_ids": [1, 2, 3]}
    ]

    body = chat(client, "今天天气怎么样")

    assert body["intent"] == "weather"
    assert body["outfits"] == []
    assert body["reply"] == "今天有点冷，加件外套。"


def test_history_is_trimmed_to_six_and_clipped(client, wardrobe, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    FakeClient.chat_queue = [{"reply": "嗯。", "intent": "chat", "occasion": None, "item_ids": []}]

    history = [{"role": "user", "content": f"第{i}句"} for i in range(8)]
    history.append({"role": "user", "content": "长" * 500})

    body = chat(client, "你好，今天好累", history=history)

    assert body["intent"] == "chat"
    messages = FakeClient.last_messages or []
    contents = [msg["content"] for msg in messages]
    # system + 10 条 few-shot + 6 条 history + 本轮 user
    assert len(messages) == 1 + 10 + 6 + 1
    assert contents[0].startswith("你是用户衣柜里的管家")
    # history 段（索引 11..16）每条都截断到 200 字以内
    assert all(len(text) <= 200 for text in contents[11:17])


# --- W12：组不出套时给事实性建议 -------------------------------------------


def make_items(client, spec):
    ids = []
    for category, occasion in spec:
        res = client.post(
            "/api/items",
            json={"category": category, "warmth": 2, "occasion": [occasion] if occasion else []},
        )
        ids.append(res.json()["id"])
    return ids


def test_empty_outfit_reply_has_real_counts(client, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    make_items(client, [("top", None), ("bottom", None), ("shoes", "casual")])
    FakeClient.chat_queue = [
        {"reply": "面试就穿那件上衣吧。", "intent": "recommend", "occasion": "formal", "item_ids": []},
        {"reply": "面试就穿那件上衣吧。", "intent": "recommend", "occasion": "formal", "item_ids": []},
    ]

    body = chat(client, "明天面试穿什么")

    assert body["intent"] == "recommend"
    assert body["outfits"] == []
    assert "1 件能穿的上衣" in body["reply"]
    assert "0 双鞋" in body["reply"]
    assert "面试就穿那件上衣吧" not in body["reply"]


def test_empty_outfit_with_no_usable_items_says_so(client, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    make_items(client, [("top", "casual"), ("bottom", "casual"), ("shoes", "casual")])
    FakeClient.chat_queue = [
        {"reply": "穿那件。", "intent": "recommend", "occasion": "formal", "item_ids": []},
        {"reply": "穿那件。", "intent": "recommend", "occasion": "formal", "item_ids": []},
    ]

    body = chat(client, "明天面试穿什么")

    assert body["outfits"] == []
    assert "一件能穿的都没有" in body["reply"]
    assert "穿那件" not in body["reply"]


def test_non_empty_outfits_keep_model_reply(client, wardrobe, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    top, bottom, shoes, outer = wardrobe[0], wardrobe[2], wardrobe[4], wardrobe[6]
    FakeClient.chat_queue = [
        {
            "reply": "这套挺利索。",
            "intent": "recommend",
            "occasion": "casual",
            "item_ids": [top, bottom, shoes, outer],
        }
    ]

    body = chat(client, "我晚点要约会")

    assert body["outfits"]
    assert body["reply"] == "这套挺利索。"


def test_relax_phrase_ignores_occasion(client):
    make_items(client, [("top", "casual"), ("bottom", "casual"), ("shoes", "casual")])

    body = chat(client, "随便配一套", occasion="formal")

    assert body["occasion"] is None
    assert body["outfits"]


# --- W13：寒暄不该被当成问天气 ---------------------------------------------


def test_greeting_parses_as_chat(client):
    from app.chat import parse_intent_rules

    assert parse_intent_rules("你好").intent == "chat"
    assert parse_intent_rules("在吗").intent == "chat"
    assert parse_intent_rules("谢谢啦").intent == "chat"


def test_greeting_with_weather_word_is_still_weather(client):
    from app.chat import parse_intent_rules

    assert parse_intent_rules("你好，今天冷吗").intent == "weather"
    assert parse_intent_rules("你好，今天多少度").intent == "weather"


def test_greeting_endpoint_does_not_report_numbers(client, wardrobe, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    FakeClient.chat_queue = [
        {
            "reply": "你好呀，今天雾蒙蒙的有点凉，出门记得加件外套。",
            "intent": "chat",
            "occasion": None,
            "item_ids": [],
        }
    ]

    body = chat(client, "你好")

    assert body["intent"] == "chat"
    assert body["outfits"] == []
    assert not any(ch.isdigit() for ch in body["reply"])


def test_greeting_variants_parse_as_chat(client):
    from app.chat import parse_intent_rules

    for phrase in ("嗨", "哈喽", "哈啰", "早啊", "早安", "午安", "晚安"):
        assert parse_intent_rules(phrase).intent == "chat", phrase

    # 带了推荐词就不算纯寒暄
    assert parse_intent_rules("哈喽，今天穿什么").intent == "recommend"


# --- W16：备注参与选品 -----------------------------------------------------


def test_note_item_can_be_picked_and_mentioned(client, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    ids = make_items(
        client,
        [("top", None), ("bottom", None), ("shoes", None), ("outer", None)],
    )
    top, bottom, shoes, outer = ids
    # 给外套写一句只有用户知道的备注
    client.patch(f"/api/items/{outer}", json={"note": "女朋友送的"})

    FakeClient.chat_queue = [
        {
            "reply": "外面有点凉，那件你对象送的外套正好披上。",
            "intent": "recommend",
            "occasion": "casual",
            "item_ids": [top, bottom, shoes, outer],
        }
    ]

    body = chat(client, "今晚和对象出去吃饭")

    assert body["source"] == "llm"
    assert body["reply"] == "外面有点凉，那件你对象送的外套正好披上。"
    picked = {item["id"] for item in body["outfits"][0]["items"]}
    assert outer in picked
    # 备注进了 prompt，但没有以结构化字段的形式插在中间
    prompt = FakeClient.last_messages[-1]["content"]
    assert "备注：女朋友送的" in prompt


def test_without_key_notes_are_ignored(client, monkeypatch):
    ids = make_items(client, [("top", None), ("bottom", None), ("shoes", None)])
    client.patch(f"/api/items/{ids[0]}", json={"note": "女朋友送的"})

    body = chat(client, "今晚和对象出去吃饭")

    assert body["outfits"]  # 规则路径照常出结果
    assert FakeClient.chat_calls == 0


# --- W17b：对话里识别地点与温度 -------------------------------------------


def test_city_in_message_overrides_default(client, wardrobe):
    body = chat(client, "我在上海，今天穿什么")

    assert body["outfits"]
    weather_step = next(step for step in body["trace"] if step["tool"] == "get_weather")
    assert weather_step["summary"].startswith("上海")
    assert "上海" in body["reply"]


def test_temperature_in_message_skips_upstream(client, wardrobe):
    body = chat(client, "今天大概 15 到 25 度")

    assert FakeClient.weather_calls == 0  # 不取上游
    assert body["outfits"]
    assert "15–25" in body["reply"]


def test_far_place_asks_for_temperature_and_shows_no_cards(client, wardrobe):
    body = chat(client, "我要去澳洲玩，带什么衣服")

    assert body["outfits"] == []
    assert "取不到" in body["reply"]
    assert "度" in body["reply"]
    assert body["fallback_reason"] == "weather_unavailable"


def test_metaphor_city_does_not_switch_city(client, wardrobe):
    body = chat(client, "像北京那样冷")
    weather_step = next(step for step in body["trace"] if step["tool"] == "get_weather")
    assert weather_step["summary"].startswith("杭州")


def test_single_temperature_makes_cold_outfit(client, wardrobe):
    body = chat(client, "明天 5 度")

    assert FakeClient.weather_calls == 0
    assert body["outfits"]
    first = body["outfits"][0]["items"]
    assert any(item["category"] == "outer" for item in first)


def test_two_digit_temperature_is_not_split(client, wardrobe):
    """「28 度」不能被拆成 2–8 度。"""
    body = chat(client, "那边大概 28 度")

    assert "28" in body["reply"]
    assert "2–8" not in body["reply"]
    assert body["outfits"]
    first = body["outfits"][0]["items"]
    # 28 度不需要外套
    assert not any(item["category"] == "outer" for item in first)
