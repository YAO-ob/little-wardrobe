"""搭配保存接口测试：落库、layer 填充、校验、列表。"""

from __future__ import annotations

from datetime import date

from app.models import Outfit, OutfitItem


def _item(client, category: str, **extra) -> dict:
    res = client.post("/api/items", json={"category": category, **extra})
    assert res.status_code == 201, res.text
    return res.json()


def _weather() -> dict:
    return {
        "date": "2026-11-21",
        "t_min": 6.8,
        "t_max": 14.6,
        "feels_min": 4.1,
        "feels_max": 11.9,
        "precip_prob": 0.0,
        "wind": 9.7,
        "uv": 4.45,
        "weather_code": 0,
        "weather_text": "晴",
    }


def test_create_outfit_writes_rows_and_layers(client):
    top = _item(client, "top")
    bottom = _item(client, "bottom")
    shoes = _item(client, "shoes")
    outer = _item(client, "outer")

    res = client.post(
        "/api/outfits",
        json={
            "item_ids": [top["id"], bottom["id"], shoes["id"], outer["id"]],
            "weather": _weather(),
            "note": "今天穿这套",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["worn_on"] == "2026-11-21"
    assert body["item_ids"] == [top["id"], bottom["id"], shoes["id"], outer["id"]]

    # 直接查库：outfit_items 四行，layer 按品类推导
    from app.db import SessionLocal

    with SessionLocal() as db:
        outfit = db.get(Outfit, body["id"])
        assert outfit is not None
        assert outfit.worn_on == "2026-11-21"
        assert outfit.weather_json and "weather_text" in outfit.weather_json
        links = db.query(OutfitItem).filter(OutfitItem.outfit_id == outfit.id).all()
        layers = {link.item_id: link.layer for link in links}
        assert layers == {
            top["id"]: "inner",
            bottom["id"]: None,
            shoes["id"]: None,
            outer["id"]: "outer",
        }


def test_create_outfit_without_weather_uses_today(client):
    item = _item(client, "top")
    res = client.post("/api/outfits", json={"item_ids": [item["id"]]})
    assert res.status_code == 201
    assert res.json()["worn_on"] == date.today().isoformat()


def test_empty_item_ids_is_rejected(client):
    res = client.post("/api/outfits", json={"item_ids": []})
    assert res.status_code == 422


def test_unknown_or_deleted_item_is_rejected(client):
    item = _item(client, "top")
    client.delete(f"/api/items/{item['id']}")

    res = client.post("/api/outfits", json={"item_ids": [item["id"]]})
    assert res.status_code == 422
    assert "不存在或已删除" in res.json()["detail"]

    res = client.post("/api/outfits", json={"item_ids": [999999]})
    assert res.status_code == 422


def test_duplicate_item_ids_are_collapsed(client):
    item = _item(client, "top")
    res = client.post("/api/outfits", json={"item_ids": [item["id"], item["id"]]})
    assert res.status_code == 201
    assert res.json()["item_ids"] == [item["id"]]


def test_same_outfit_twice_creates_two_rows(client):
    top = _item(client, "top")
    before = client.get("/api/outfits").json()["total"]

    first = client.post("/api/outfits", json={"item_ids": [top["id"]]})
    second = client.post("/api/outfits", json={"item_ids": [top["id"]]})

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert client.get("/api/outfits").json()["total"] == before + 2


def test_list_outfits_returns_item_ids(client):
    top = _item(client, "top")
    bottom = _item(client, "bottom")
    created = client.post(
        "/api/outfits", json={"item_ids": [top["id"], bottom["id"]]}
    ).json()

    listing = client.get("/api/outfits", params={"limit": 20}).json()
    assert listing["total"] >= 1
    row = next(o for o in listing["outfits"] if o["id"] == created["id"])
    assert row["item_ids"] == [top["id"], bottom["id"]]
