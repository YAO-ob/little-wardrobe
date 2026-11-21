"""HEIC/HEIF 支持测试：iPhone 直出的照片要能进得来。"""

from __future__ import annotations

import io

from PIL import Image

from app import imaging  # 触发 register_heif_opener()


def _heic_bytes(size: tuple[int, int] = (1200, 900)) -> bytes:
    img = Image.new("RGB", size, (30, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="HEIF", quality=90)
    return buf.getvalue()


def test_heic_suffix_is_allowed():
    assert ".heic" in imaging.ALLOWED_SUFFIXES
    assert ".heif" in imaging.ALLOWED_SUFFIXES


def test_upload_heic_generates_two_webp(client):
    res = client.post("/api/images", files={"file": ("iphone.heic", _heic_bytes(), "image/heic")})

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["url"].endswith("_1024.webp")
    assert body["thumb_url"].endswith("_256.webp")
    assert body["width"] == 1024
    assert client.get(body["url"]).status_code == 200
    assert client.get(body["thumb_url"]).status_code == 200


def test_corrupt_heic_is_415_and_leaves_no_tmp_file(client):
    from app.config import get_settings

    settings = get_settings()
    settings.ensure_dirs()
    before = len(list(settings.tmp_dir.iterdir()))

    res = client.post(
        "/api/images",
        files={"file": ("broken.heic", b"this is definitely not a heic file", "image/heic")},
    )

    assert res.status_code == 415
    assert "格式" in res.json()["detail"]
    assert len(list(settings.tmp_dir.iterdir())) == before
