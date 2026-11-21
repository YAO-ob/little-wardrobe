"""城市列表接口测试。"""

from __future__ import annotations

from app.data import cities


def test_cities_endpoint_lists_builtin_cities(client):
    body = client.get("/api/cities").json()

    assert body["default"] == "杭州"
    assert "杭州" in body["cities"]
    assert len(body["cities"]) == 8


def test_cities_reflects_backend_table(client, monkeypatch):
    """加一个临时城市，接口应该立刻能看到（monkeypatch 结束自动还原）。"""
    monkeypatch.setitem(
        cities.CITIES,
        "测试城",
        cities.City("测试城", 30.0, 120.0, "Asia/Shanghai"),
    )

    body = client.get("/api/cities").json()
    assert "测试城" in body["cities"]
    assert len(body["cities"]) == 9
