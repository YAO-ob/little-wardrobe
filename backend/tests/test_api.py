"""接口测试：上传 → 建单品 → 列表筛选 → 更新 → 删除。"""

from __future__ import annotations

import io

from PIL import Image

from app.config import get_settings


def _jpeg(width: int = 800, height: int = 800, color=(120, 90, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _upload(client, name: str = "a.jpg") -> dict:
    res = client.post(
        "/api/images",
        files={"file": (name, _jpeg(), "image/jpeg")},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_upload_returns_two_sizes(client):
    image = _upload(client)
    assert image["url"].endswith("_1024.webp")
    assert image["thumb_url"].endswith("_256.webp")
    assert client.get(image["url"]).status_code == 200
    assert client.get(image["thumb_url"]).status_code == 200


def _media_counts() -> tuple[int, int, int]:
    settings = get_settings()
    settings.ensure_dirs()
    return (
        len(list(settings.originals_dir.iterdir())),
        len(list(settings.derived_dir.iterdir())),
        len(list(settings.tmp_dir.iterdir())),
    )


def test_upload_only_touches_tmp(client):
    """上传但不建单品：正式目录零新增，tmp 里躺着 原图 + 两档。"""
    assert _media_counts() == (0, 0, 0)

    image = _upload(client)

    assert image["url"].startswith("/media/tmp/")
    assert image["thumb_url"].startswith("/media/tmp/")
    assert _media_counts() == (0, 0, 3)


def test_attach_promotes_files_out_of_tmp(client):
    """建单品成功后：tmp 清空，原图进 originals，两档进 derived，url 能打开。"""
    image = _upload(client)
    assert _media_counts() == (0, 0, 3)

    item = client.post(
        "/api/items",
        json={"category": "top", "image_ids": [image["id"]]},
    ).json()

    assert _media_counts() == (1, 2, 0)
    assert item["image"]["url"].startswith("/media/derived/")
    assert client.get(item["image"]["url"]).status_code == 200
    assert client.get(item["image"]["thumb_url"]).status_code == 200


def test_image_ids_validation_does_not_move_files(client):
    """挂图失败时不能把文件搬走。"""
    stale = _upload(client)
    client.post("/api/items", json={"category": "top", "image_ids": [stale["id"]]})

    client.post("/api/items", json={"category": "top"})
    fresh = _upload(client)

    before = _media_counts()
    res = client.post("/api/items", json={"category": "top", "image_ids": [stale["id"], fresh["id"]]})
    assert res.status_code == 422
    assert _media_counts() == before


def test_reject_non_image(client):
    res = client.post("/api/images", files={"file": ("note.txt", b"hello", "text/plain")})
    assert res.status_code == 415


def test_reject_corrupted_image(client):
    res = client.post("/api/images", files={"file": ("broken.jpg", b"xxxx", "image/jpeg")})
    assert res.status_code == 415


def test_create_and_list(client):
    image = _upload(client)
    res = client.post(
        "/api/items",
        json={"category": "bottom", "warmth": 3, "occasion": ["work"], "image_ids": [image["id"]]},
    )
    assert res.status_code == 201, res.text
    item = res.json()
    assert item["category"] == "bottom"
    assert item["image"]["id"] == image["id"]
    assert item["name"] == "下装"  # 无名字时按品类兜底

    listing = client.get("/api/items", params={"category": "bottom"}).json()
    assert listing["total"] >= 1
    assert all(i["category"] == "bottom" for i in listing["items"])


def test_incomplete_filter(client):
    # 配饰没有厚薄概念：颜色 + 场合填齐就算完整，不因 warmth 缺失被标红
    accessory = client.post(
        "/api/items", json={"category": "accessory", "color_family": "black", "occasion": ["casual"]}
    ).json()
    # 上衣核心字段（颜色 / 场合 / 厚薄）齐全 → 完整
    complete = client.post(
        "/api/items",
        json={"category": "top", "color_family": "black", "occasion": ["casual"], "warmth": 2},
    ).json()
    # 缺颜色 / 缺场合 / 缺厚薄 → 都该被标出来
    client.post("/api/items", json={"category": "top", "occasion": ["casual"], "warmth": 2})
    client.post("/api/items", json={"category": "top", "color_family": "black", "warmth": 2})
    client.post("/api/items", json={"category": "top", "color_family": "black", "occasion": ["casual"]})

    listing = client.get("/api/items", params={"incomplete": "true"}).json()
    ids = {item["id"] for item in listing["items"]}
    assert accessory["id"] not in ids
    assert complete["id"] not in ids
    assert len(ids) >= 3


def test_missing_staged_file_fails_loudly(client):
    """暂存文件被删掉后再建单品：必须 500，且不留下半个单品。"""
    image = _upload(client)
    settings = get_settings()
    for path in settings.tmp_dir.iterdir():
        path.unlink()

    total_before = client.get("/api/items", params={"limit": 1}).json()["total"]
    res = client.post("/api/items", json={"category": "top", "image_ids": [image["id"]]})

    assert res.status_code == 500
    assert "暂存文件丢失" in res.json()["detail"]
    assert client.get("/api/items", params={"limit": 1}).json()["total"] == total_before
    assert list(settings.originals_dir.iterdir()) == []
    assert list(settings.derived_dir.iterdir()) == []


def test_image_id_must_be_unclaimed(client):
    image = _upload(client)
    first = client.post("/api/items", json={"category": "top", "image_ids": [image["id"]]})
    assert first.status_code == 201

    second = client.post("/api/items", json={"category": "top", "image_ids": [image["id"]]})
    assert second.status_code == 422


def test_patch_accepts_all_editable_fields(client):
    item = client.post("/api/items", json={"category": "top"}).json()

    payload = {
        "color_family": "navy",
        "color_hex": "#223344",
        "brand": "测试牌",
        "material": "棉",
        "price": 199.5,
        "formality": 4,
        "layer": "inner",
        "season": ["spring", "autumn"],
        "note": "偏薄",
        "occasion": ["work"],
    }
    res = client.patch(f"/api/items/{item['id']}", json=payload)
    assert res.status_code == 200, res.text

    body = res.json()
    for key, value in payload.items():
        assert body[key] == value, key


def test_delete_staged_image_removes_all_files(client):
    from app.config import get_settings

    settings = get_settings()
    settings.ensure_dirs()
    before = len(list(settings.tmp_dir.iterdir()))

    res = client.post("/api/images", files={"file": ("x.jpg", _jpeg(), "image/jpeg")})
    assert res.status_code == 201
    image_id = res.json()["id"]
    assert len(list(settings.tmp_dir.iterdir())) == before + 3  # 原图 + 1024 + 256

    assert client.delete(f"/api/images/{image_id}").status_code == 204

    # 原图也要一并清掉，否则「跳过」会留孤儿
    assert len(list(settings.tmp_dir.iterdir())) == before


def test_patch_and_delete(client):
    item = client.post("/api/items", json={"category": "dress"}).json()

    patched = client.patch(
        f"/api/items/{item['id']}",
        json={"color_family": "red", "season": ["summer"], "warmth": 1},
    ).json()
    assert patched["color_family"] == "red"
    assert patched["season"] == ["summer"]

    assert client.delete(f"/api/items/{item['id']}").status_code == 204
    assert client.get(f"/api/items/{item['id']}").status_code == 404
