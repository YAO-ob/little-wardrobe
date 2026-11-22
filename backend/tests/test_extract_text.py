"""W20：纯文字录入识别（extract-text）与 description 列读写。上游全部 mock，不联网。"""

from __future__ import annotations

import json

import httpx
import pytest

CONFIG_OK = {
    "category": "top",
    "warmth": 1,
    "color_family": "beige",
    "occasion": ["work"],
    "material": "亚麻",
    "confidence": 0.9,
}


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
    FakeClient.calls = []
    FakeClient.response = completion(json.dumps(CONFIG_OK))
    FakeClient.error = None
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setenv("EW_LLM_KEY", "test-key")
    monkeypatch.delenv("EW_CLASSIFY_MIN_CONFIDENCE", raising=False)
    yield


def extract(client, text: str, key: str | None = "k") -> dict:
    headers = {"X-LLM-Key": key} if key else {}
    res = client.post("/api/items/extract-text", json={"text": text}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_extract_text_returns_all_fields(client):
    body = extract(client, "米白色亚麻长袖衬衫，夏天穿，通勤也能穿")

    assert body == {
        "category": "top",
        "warmth": 1,
        "color_family": "beige",
        "occasion": ["work"],
        "material": "亚麻",
        "confidence": 0.9,
        "source": "llm",
        "reason": None,
    }


def test_bad_color_keeps_category_and_material(client):
    """逐字段容错：颜色越界只丢颜色，品类/材质照常返回（复用 classify 的逻辑）。"""
    FakeClient.response = completion(
        json.dumps({**CONFIG_OK, "color_family": "charcoal"})
    )

    body = extract(client, "灰亚麻衬衫")

    assert body["category"] == "top"
    assert body["material"] == "亚麻"
    assert body["color_family"] is None
    assert body["reason"] == "invalid_label"
    assert body["source"] == "llm"


def test_low_confidence_drops_everything_including_material(client):
    """置信度 < 0.6 → 全部置 null，材质也不例外。"""
    FakeClient.response = completion(json.dumps({**CONFIG_OK, "confidence": 0.3}))

    body = extract(client, "随便写的")

    assert body["category"] is None
    assert body["material"] is None
    assert body["confidence"] == 0.3
    assert body["reason"] == "low_confidence"
    assert body["source"] == "none"


def test_missing_key_returns_none_without_calling_upstream(client, monkeypatch):
    monkeypatch.delenv("EW_LLM_KEY", raising=False)

    body = extract(client, "亚麻衬衫", key=None)

    assert body["source"] == "none"
    assert body["reason"] == "no_key"
    assert FakeClient.calls == []


def test_empty_text_with_key_does_not_call_upstream(client):
    body = extract(client, "   ")

    assert body["source"] == "none"
    assert body["reason"] == "empty_text"
    assert FakeClient.calls == []


def test_timeout_returns_reason_without_500(client):
    FakeClient.error = httpx.ReadTimeout("slow")

    body = extract(client, "亚麻衬衫")

    assert body["reason"] == "timeout"
    assert body["source"] == "none"


def test_text_over_300_chars_is_truncated(client):
    long_text = "字" * 400
    extract(client, long_text)

    assert len(FakeClient.calls) == 1
    user_content = FakeClient.calls[0]["json"]["messages"][1]["content"]
    # 发给上游的描述部分被截到 300 字
    sent = user_content.rsplit("\n", 1)[-1]
    assert len(sent) == 300
    assert sent == "字" * 300


def test_description_is_written_and_read_back(client):
    """迁移后 description 列可读写：创建 → 列表 → 详情 → 更新。"""
    res = client.post(
        "/api/items",
        json={"category": "top", "description": "米白色亚麻长袖衬衫"},
    )
    assert res.status_code == 201, res.text
    item = res.json()
    item_id = item["id"]
    assert item["description"] == "米白色亚麻长袖衬衫"

    listed = client.get("/api/items").json()
    match = next(i for i in listed["items"] if i["id"] == item_id)
    assert match["description"] == "米白色亚麻长袖衬衫"

    detail = client.get(f"/api/items/{item_id}").json()
    assert detail["description"] == "米白色亚麻长袖衬衫"

    patched = client.patch(
        f"/api/items/{item_id}", json={"description": "改成了纯棉 T 恤"}
    ).json()
    assert patched["description"] == "改成了纯棉 T 恤"

    # 不传 description 不会把已有值清掉（exclude_unset）
    kept = client.patch(f"/api/items/{item_id}", json={"note": "新备注"}).json()
    assert kept["description"] == "改成了纯棉 T 恤"
    assert kept["note"] == "新备注"


def test_description_over_300_chars_is_truncated_on_save(client):
    res = client.post(
        "/api/items", json={"category": "top", "description": "字" * 400}
    )
    assert res.status_code == 201, res.text
    assert len(res.json()["description"]) == 300
