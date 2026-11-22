"""把库里的中文颜色统一成英文枚举（一次性）。

默认 dry-run：只打印「旧值 → 新值」的分布；--apply 才写库。
映射不到的置 null，之后可以用 scripts/backfill_colors.py 重新识别。

单独跑一次，不塞进 alembic：数据修复不属于 schema 迁移。
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Item, utcnow  # noqa: E402
from app.schemas import COLOR_FAMILIES  # noqa: E402

# 子串匹配，先长后短：'米白' 不能被 '白' 先吃掉
COLOR_MAP: dict[str, str] = {
    "米白": "beige",
    "米": "beige",
    "杏": "beige",
    "藕粉": "pink",
    "咖啡": "brown",
    "藏青": "navy",
    "深蓝": "navy",
    "海军蓝": "navy",
    "天蓝": "blue",
    "草绿": "green",
    "墨绿": "green",
    "酒红": "red",
    "条纹": "multi",
    "格纹": "multi",
    "多色": "multi",
    "花": "multi",
    "黑": "black",
    "白": "white",
    "灰": "gray",
    "棕": "brown",
    "咖": "brown",
    "蓝": "blue",
    "绿": "green",
    "红": "red",
    "粉": "pink",
    "紫": "purple",
    "黄": "yellow",
    "橙": "orange",
    "橘": "orange",
}

ORDERED_KEYS = sorted(COLOR_MAP, key=len, reverse=True)


def map_color(raw: str | None) -> str | None:
    """中文/混写 → 英文枚举；已经是枚举则原样返回；映射不到返回 None。"""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if text in COLOR_FAMILIES:
        return text
    if text.lower() in COLOR_FAMILIES:
        return text.lower()
    for key in ORDERED_KEYS:
        if key in text:
            return COLOR_MAP[key]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="统一 color_family 为英文枚举（默认 dry-run）")
    parser.add_argument("--apply", action="store_true", help="真的写库")
    args = parser.parse_args()

    with SessionLocal() as db:
        rows = db.execute(select(Item).where(Item.color_family.is_not(None))).scalars().all()
        changes: list[tuple[Item, str | None]] = []
        for row in rows:
            mapped = map_color(row.color_family)
            if mapped != row.color_family:
                changes.append((row, mapped))

        stats = Counter((row.color_family, mapped) for row, mapped in changes)

        print(f"需要改的 {len(changes)} 件，共 {len(stats)} 种映射：")
        for (old, new), count in sorted(stats.items(), key=lambda pair: -pair[1]):
            print(f"  {old!r} → {new!r}  {count} 条")

        if not changes:
            print("没有需要迁移的数据")
            return 0

        if not args.apply:
            print("dry-run：没有写库，加 --apply 才执行")
            return 0

        for row, mapped in changes:
            row.color_family = mapped
            row.updated_at = utcnow()
        db.commit()
        print(f"已更新 {len(changes)} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
