"""W8a：尺码 / 购买链接 / 洗护说明 / 洗护符号。"""

from __future__ import annotations

from app.schemas import CARE_SYMBOLS


def test_new_columns_exist_and_roundtrip(client):
    item = client.post("/api/items", json={"category": "top"}).json()

    res = client.patch(
        f"/api/items/{item['id']}",
        json={
            "size": "M",
            "purchase_url": "https://example.com/item/1",
            "care_text": "30 度机洗，不要漂白",
            "care_symbols": ["wash_30", "no_bleach"],
        },
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["size"] == "M"
    assert body["purchase_url"] == "https://example.com/item/1"
    assert body["care_text"] == "30 度机洗，不要漂白"
    assert body["care_symbols"] == ["wash_30", "no_bleach"]

    # 重新读一次，确认真的落库了（不是只回显）
    again = client.get(f"/api/items/{item['id']}").json()
    assert again["care_symbols"] == ["wash_30", "no_bleach"]


def test_care_symbol_table_has_twelve_codes():
    assert len(CARE_SYMBOLS) == 12
    assert "no_dry_clean" in CARE_SYMBOLS


def test_unknown_care_symbol_is_rejected(client):
    item = client.post("/api/items", json={"category": "top"}).json()

    res = client.patch(f"/api/items/{item['id']}", json={"care_symbols": ["wash_30", "wash_60"]})

    assert res.status_code == 422
    assert "wash_60" in res.text


def test_purchase_url_length_is_limited(client):
    item = client.post("/api/items", json={"category": "top"}).json()

    too_long = "https://example.com/" + "a" * 500
    res = client.patch(f"/api/items/{item['id']}", json={"purchase_url": too_long})

    assert res.status_code == 422


def test_care_symbols_default_to_empty_list(client):
    item = client.post("/api/items", json={"category": "top"}).json()
    assert item["care_symbols"] == []
    assert item["size"] is None


def test_exclusive_group_rejects_two(client):
    item = client.post("/api/items", json={"category": "top"}).json()

    res = client.patch(
        f"/api/items/{item['id']}", json={"care_symbols": ["bleach_ok", "no_bleach"]}
    )

    assert res.status_code == 422
    assert "互斥" in res.text


def test_one_symbol_per_group_is_fine(client):
    item = client.post("/api/items", json={"category": "top"}).json()

    res = client.patch(
        f"/api/items/{item['id']}",
        json={"care_symbols": ["wash_40", "no_bleach", "no_tumble", "iron_low"]},
    )

    assert res.status_code == 200, res.text
    assert res.json()["care_symbols"] == ["wash_40", "no_bleach", "no_tumble", "iron_low"]


# --- W15：颜色只认英文枚举 -------------------------------------------------


def test_patch_chinese_color_is_422(client):
    item = client.post("/api/items", json={"category": "top"}).json()
    res = client.patch(f"/api/items/{item['id']}", json={"color_family": "白"})
    assert res.status_code == 422
    assert "white" in res.text


def test_patch_english_color_is_200(client):
    item = client.post("/api/items", json={"category": "top"}).json()
    res = client.patch(f"/api/items/{item['id']}", json={"color_family": "white"})
    assert res.status_code == 200
    assert res.json()["color_family"] == "white"


def test_item_out_hides_legacy_dirty_value(client):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Item

    item = client.post("/api/items", json={"category": "top"}).json()
    with SessionLocal() as db:
        row = db.execute(select(Item).where(Item.id == item["id"])).scalar_one()
        row.color_family = "米白"  # 绕过校验直接写库，模拟历史脏数据
        db.commit()

    body = client.get(f"/api/items/{item['id']}").json()
    assert body["color_family"] is None


def test_migrate_colors_mapping():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("migrate_colors", root / "scripts" / "migrate_colors.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.map_color("白") == "white"
    assert module.map_color("米白") == "beige"
    assert module.map_color("藏青") == "navy"
    assert module.map_color("草绿色") == "green"
    assert module.map_color("条纹") == "multi"
    assert module.map_color("black") == "black"
    assert module.map_color("莫兰迪色") is None
    assert module.map_color(None) is None
