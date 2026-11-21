"""W7a：录入预填（品类/厚薄）。上游全部 mock，不联网。"""

from __future__ import annotations

import base64
import io
import json

import httpx
import pytest
from PIL import Image

from app.routers import classify

CONFIG_OK = {"category": "shoes", "warmth": 2, "confidence": 0.9}


class FakeResponse:
    def __init__(self, payload: dict | None = None, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def completion(content: str, finish_reason: str = "stop") -> FakeResponse:
    return FakeResponse(
        {
            "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
    )


class FakeClient:
    calls: list[dict] = []
    response: FakeResponse | None = None
    error: Exception | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        FakeClient.calls.append({"url": url, "json": json, "headers": headers})
        if FakeClient.error is not None:
            raise FakeClient.error
        assert FakeClient.response is not None
        return FakeClient.response


@pytest.fixture(autouse=True)
def fake_upstream(monkeypatch):
    classify.clear_cache()
    FakeClient.calls = []
    FakeClient.response = completion(json.dumps(CONFIG_OK))
    FakeClient.error = None
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    monkeypatch.delenv("EW_CLASSIFY_MIN_CONFIDENCE", raising=False)
    yield
    classify.clear_cache()


def make_image(client) -> int:
    buf = io.BytesIO()
    Image.new("RGB", (1600, 1200), (200, 40, 40)).save(buf, "PNG")
    res = client.post("/api/images", files={"file": ("shoe.png", buf.getvalue(), "image/png")})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def classify_image(client, image_id: int, key: str | None = "k") -> dict:
    headers = {"X-LLM-Key": key} if key else {}
    res = client.post("/api/classify", json={"image_id": image_id}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_classify_returns_llm_result(client):
    image_id = make_image(client)

    body = classify_image(client, image_id)

    assert body == {
        "category": "shoes",
        "warmth": 2,
        "confidence": 0.9,
        "source": "llm",
        "reason": None,
    }


def test_low_confidence_is_dropped(client):
    FakeClient.response = completion(
        json.dumps({"category": "shoes", "warmth": 2, "confidence": 0.4})
    )

    body = classify_image(client, make_image(client))

    assert body["category"] is None
    assert body["warmth"] is None
    assert body["confidence"] == 0.4
    assert body["reason"] == "low_confidence"
    assert body["source"] == "none"


def test_invalid_label_is_dropped(client):
    FakeClient.response = completion(
        json.dumps({"category": "hat", "warmth": 2, "confidence": 0.9})
    )

    body = classify_image(client, make_image(client))

    assert body["category"] is None
    assert body["reason"] == "invalid_label"


def test_missing_key_does_not_call_upstream(client, monkeypatch):
    monkeypatch.delenv("EW_LLM_KEY", raising=False)

    body = classify_image(client, make_image(client), key=None)

    assert body["source"] == "none"
    assert body["reason"] == "no_key"
    assert FakeClient.calls == []


def test_timeout_returns_reason_without_500(client):
    FakeClient.error = httpx.ReadTimeout("slow")

    body = classify_image(client, make_image(client))

    assert body["reason"] == "timeout"
    assert body["source"] == "none"


def test_non_json_returns_bad_json(client):
    FakeClient.response = completion("这不是 JSON")

    body = classify_image(client, make_image(client))

    assert body["reason"] == "bad_json"


def test_result_is_cached_per_image(client):
    image_id = make_image(client)

    first = classify_image(client, image_id)
    second = classify_image(client, image_id)

    assert first == second
    assert len(FakeClient.calls) == 1


def test_sent_image_is_downscaled_jpeg(client):
    classify_image(client, make_image(client))

    payload = FakeClient.calls[0]["json"]
    content = payload["messages"][1]["content"]
    image_url = next(part["image_url"]["url"] for part in content if part["type"] == "image_url")

    assert image_url.startswith("data:image/jpeg;base64,")
    raw = base64.b64decode(image_url.split(",", 1)[1])
    with Image.open(io.BytesIO(raw)) as sent:
        assert sent.format == "JPEG"
        assert max(sent.size) <= 512
