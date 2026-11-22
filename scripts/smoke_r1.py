"""R1 冒烟测试：上传图片 → 建单品 → 列表 → 取缩略图。

用法（服务已在 127.0.0.1:8000 运行）：
    python scripts/smoke_r1.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import httpx
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"


def make_jpeg(width: int = 1200, height: int = 1600) -> bytes:
    img = Image.new("RGB", (width, height), (90, 120, 160))
    for x in range(0, width, 40):
        for y in range(0, height, 40):
            if (x // 40 + y // 40) % 2 == 0:
                img.paste((230, 230, 235), (x, y, min(x + 40, width), min(y + 40, height)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=20) as client:
        health = client.get("/healthz")
        print("healthz:", health.status_code, health.json())

        jpeg = make_jpeg()
        upload = client.post(
            "/api/images",
            files={"file": ("test.jpg", jpeg, "image/jpeg")},
        )
        print("upload:", upload.status_code, upload.text[:200])
        if upload.status_code != 201:
            return 1
        image = upload.json()

        created = client.post(
            "/api/items",
            json={
                "category": "top",
                "warmth": 2,
                "occasion": "casual",
                "image_ids": [image["id"]],
            },
        )
        print("create:", created.status_code, created.text[:300])
        if created.status_code != 201:
            return 1
        item = created.json()

        listing = client.get("/api/items")
        print("list:", listing.status_code, "total =", listing.json()["total"])

        thumb = client.get(item["image"]["thumb_url"])
        print("thumb:", thumb.status_code, len(thumb.content), "bytes", thumb.headers.get("content-type"))

        display = client.get(item["image"]["url"])
        print("display:", display.status_code, len(display.content), "bytes")

        if listing.json()["total"] < 1 or thumb.status_code != 200 or display.status_code != 200:
            print("FAIL: 衣柜链路不通")
            return 1

    print("R1 SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
