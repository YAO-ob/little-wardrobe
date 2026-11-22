"""给颜色为空的单品补 color_family（复用 classify 的逻辑，不打 HTTP）。

默认 dry-run，只打印将处理多少件；--apply 才写库。只改 color_family 一个字段。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.llm import LLMError, resolve_llm_config  # noqa: E402
from app.models import Item, utcnow  # noqa: E402
from app.routers.classify import classify_path  # noqa: E402

SLEEP_SECONDS = 0.3


def load_candidates() -> list[tuple[int, list[tuple[str, bool]]]]:
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(Item)
                .options(selectinload(Item.images))
                .where(Item.color_family.is_(None), Item.deleted_at.is_(None))
                .order_by(Item.id)
            )
            .scalars()
            .all()
        )
        return [
            (row.id, [(img.path, bool(img.is_primary)) for img in row.images])
            for row in rows
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description="补齐单品颜色家族（默认 dry-run）")
    parser.add_argument("--apply", action="store_true", help="真的写库（默认只统计）")
    args = parser.parse_args()

    settings = get_settings()
    candidates = load_candidates()
    print(f"将处理 {len(candidates)} 件（color_family 为空且未软删）")

    if not candidates:
        return 0

    if not args.apply:
        print("dry-run：没有写库，加 --apply 才执行")
        return 0

    config = resolve_llm_config(None)
    if config is None:
        print("没有 key：请先设置 EW_LLM_KEY 再跑。", file=sys.stderr)
        return 2

    done = 0
    skipped = 0
    failed = 0

    for item_id, images in candidates:
        # 优先主图 / 1024 展示图
        path = None
        for rel, is_primary in sorted(images, key=lambda pair: not pair[1]):
            candidate = settings.media_dir / rel
            if candidate.exists():
                path = candidate
                break
        if path is None:
            failed += 1
            print(f"  item={item_id} 没有可用图片，跳过")
            continue

        try:
            result = asyncio.run(classify_path(path, config))
        except LLMError as exc:
            failed += 1
            print(f"  item={item_id} 调用失败：{exc.reason}")
            time.sleep(SLEEP_SECONDS)
            continue
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  item={item_id} 异常：{type(exc).__name__}")
            time.sleep(SLEEP_SECONDS)
            continue

        if result.color_family:
            with SessionLocal() as db:
                row = db.get(Item, item_id)
                if row is not None:
                    row.color_family = result.color_family
                    row.updated_at = utcnow()
                    db.commit()
            done += 1
            print(f"  item={item_id} -> {result.color_family}")
        else:
            skipped += 1
            print(f"  item={item_id} 弃答（{result.reason or 'no_color'}）")

        time.sleep(SLEEP_SECONDS)

    print(f"\n成功 {done} / 弃答 {skipped} / 失败 {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
