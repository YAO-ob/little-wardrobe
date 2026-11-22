"""W6b：对话入口（意图 + 工具链）。天气与模型上游全部 mock。"""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import delete

from app import limits, llm_cache, weather
from app.db import SessionLocal
from app.models import WeatherSnapshotRow

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
    chat_reply: dict | None = None
    chat_calls = 0
    weather_calls = 0

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
        content = json_module.dumps(FakeClient.chat_reply or {})
        return FakeResponse(
            {
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 10},
            }
        )


json_module = json


@pytest.fixture(autouse=True)
def fake_upstream(monkeypatch):
    FakeClient.chat_reply = None
    FakeClient.chat_calls = 0
    FakeClient.weather_calls = 0
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.delenv("EW_LLM_KEY", raising=False)
    llm_cache.clear()
    limits.clear()
    weather.clear_cache()
    weather.clear_cooldown()
    with SessionLocal() as db:
        db.execute(delete(WeatherSnapshotRow))
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
    FakeClient.chat_reply = {"intent": "recommend", "occasion": "party", "note": "派对"}

    body = chat(client, "帮我看看穿什么好")

    assert FakeClient.chat_calls == 1
    assert body["occasion"] is None  # 越界整条丢弃，保留规则结果
    assert body["intent"] == "recommend"


def test_empty_and_overlong_message_are_422(client):
    assert client.post("/api/chat", json={"message": "   "}).status_code == 422
    assert client.post("/api/chat", json={"message": "长" * 201}).status_code == 422


def test_llm_can_supply_occasion_when_rules_miss(client, wardrobe, monkeypatch):
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    FakeClient.chat_reply = {"intent": "recommend", "occasion": "sport", "note": "羽毛球"}

    body = chat(client, "帮我看看穿什么好")

    assert body["occasion"] == "sport"
    assert "羽毛球" in body["reply"]
