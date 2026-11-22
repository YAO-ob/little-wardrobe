"""W8b：购物截图信息提取。上游 mock，不联网。"""

from __future__ import annotations

import io
import json

import httpx
import pytest
from PIL import Image


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
    calls = 0
    reply: dict | None = None
    error: Exception | None = None
    last_payload: dict | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        FakeClient.calls += 1
        FakeClient.last_payload = json
        if FakeClient.error is not None:
            raise FakeClient.error
        content = json_module.dumps(FakeClient.reply or {})
        return FakeResponse(
            {
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }
        )


json_module = json


@pytest.fixture(autouse=True)
def fake_upstream(monkeypatch):
    FakeClient.calls = 0
    FakeClient.reply = {
        "brand": "优衣库",
        "price": 199.0,
        "material": "棉",
        "color_family": "藏青",
        "size": "M",
        "confidence": 0.88,
    }
    FakeClient.error = None
    FakeClient.last_payload = None
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.delenv("EW_LLM_KEY", raising=False)
    monkeypatch.delenv("EW_CLASSIFY_MIN_CONFIDENCE", raising=False)
    yield FakeClient


def screenshot() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1200, 1600), (240, 240, 240)).save(buf, "PNG")
    return buf.getvalue()


def post(client, key: str | None = "k") -> dict:
    headers = {"X-LLM-Key": key} if key else {}
    res = client.post(
        "/api/items/extract-receipt",
        files={"file": ("shot.png", screenshot(), "image/png")},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_extracts_fields(client):
    body = post(client)

    assert body["source"] == "llm"
    assert body["brand"] == "优衣库"
    assert body["price"] == 199.0
    assert body["material"] == "棉"
    assert body["size"] == "M"
    assert body["confidence"] == 0.88


def test_low_confidence_drops_everything(client):
    FakeClient.reply = {"brand": "优衣库", "price": 199.0, "confidence": 0.3}

    body = post(client)

    assert body["brand"] is None and body["price"] is None
    assert body["reason"] == "low_confidence"
    assert body["source"] == "none"


def test_text_fields_are_trimmed_and_capped(client):
    FakeClient.reply = {
        "brand": "  " + "很长" * 30 + "  ",
        "material": "  棉  ",
        "confidence": 0.9,
    }

    body = post(client)

    assert len(body["brand"]) == 32
    assert body["material"] == "棉"


def test_invalid_price_is_dropped_but_others_survive(client):
    FakeClient.reply = {"brand": "优衣库", "price": -5, "confidence": 0.9}

    body = post(client)

    assert body["price"] is None
    assert body["brand"] == "优衣库"


def test_missing_key_does_not_call_upstream(client):
    body = post(client, key=None)

    assert body["source"] == "none"
    assert body["reason"] == "no_key"
    assert FakeClient.calls == 0


def test_timeout_returns_reason(client):
    FakeClient.error = httpx.ReadTimeout("slow")

    body = post(client)

    assert body["reason"] == "timeout"
    assert body["source"] == "none"


def test_non_json_returns_bad_json(client):
    FakeClient.reply = None  # 空对象字符串 "{}" 会被当成没有字段
    res = client.post(
        "/api/items/extract-receipt",
        files={"file": ("shot.png", screenshot(), "image/png")},
        headers={"X-LLM-Key": "k"},
    )
    assert res.status_code == 200
    assert res.json()["source"] == "none"


def test_image_is_sent_as_jpeg_data_url(client):
    post(client)

    content = FakeClient.last_payload["messages"][1]["content"]
    url = next(part["image_url"]["url"] for part in content if part["type"] == "image_url")
    assert url.startswith("data:image/jpeg;base64,")


def test_garbage_file_is_not_500(client):
    res = client.post(
        "/api/items/extract-receipt",
        files={"file": ("x.png", b"not an image", "image/png")},
        headers={"X-LLM-Key": "k"},
    )

    assert res.status_code == 200
    assert res.json()["reason"] == "bad_image"
