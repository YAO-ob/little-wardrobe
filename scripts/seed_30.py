"""W1 验收脚本：模拟「30 件衣服」的保存链路，量一遍耗时。

用法（服务已在 127.0.0.1:8000 运行）：
    python scripts/seed_30.py

注意：这里量的是「保存 30 件」的后端耗时，不含人手拍照/点击的时间。
人手那部分按 3 次点击/件估计，见 DECISIONS.md 的验收记录。
"""

from __future__ import annotations

import io
import random
import sys
import time

import httpx
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK，中文会乱码

BASE = "http://127.0.0.1:8000"
COUNT = 30

CATEGORIES = ["top", "outer", "bottom", "shoes", "accessory", "dress"]
OCCASIONS = ["casual", "work", "sport", "formal"]


def fake_photo(index: int) -> bytes:
    hue = (index * 37) % 255
    img = Image.new("RGB", (1600, 1600), (hue, 120, 255 - hue))
    for step in range(0, 1600, 80):
        img.paste((255, 255, 255), (step, step, step + 40, step + 40))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def main() -> int:
    started = time.perf_counter()
    with httpx.Client(base_url=BASE, timeout=30) as client:
        for index in range(COUNT):
            upload = client.post(
                "/api/images",
                files={"file": (f"item-{index}.jpg", fake_photo(index), "image/jpeg")},
            )
            upload.raise_for_status()
            image = upload.json()

            created = client.post(
                "/api/items",
                json={
                    "category": random.choice(CATEGORIES),
                    "warmth": random.choice([1, 2, 3]),
                    "occasion": random.choice(OCCASIONS),
                    "color_family": random.choice(["黑", "白", "灰", "蓝", "棕"]),
                    "image_ids": [image["id"]],
                },
            )
            created.raise_for_status()

        elapsed = time.perf_counter() - started
        total = client.get("/api/items", params={"limit": 1}).json()["total"]

    per_item = elapsed / COUNT
    print(f"保存 {COUNT} 件耗时 {elapsed:.1f}s，平均 {per_item * 1000:.0f} ms/件")
    print(f"当前衣橱总数：{total}")
    print(f"外推（含人手操作 10s/件）：{(10 + per_item) * COUNT / 60:.1f} 分钟，目标 < 15 分钟")
    return 0


if __name__ == "__main__":
    sys.exit(main())
