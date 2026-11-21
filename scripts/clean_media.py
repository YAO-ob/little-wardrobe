"""清理不再被引用的媒体文件。

判定：可见集合 = 未被软删的单品所引用图片的路径（originals + derived）。
文件名的 stem 不在可见集合里 → 孤儿。
默认 dry-run，只统计不删；加 --apply 才真删。**不碰数据库**（以只读方式打开）。
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "wardrobe.db"
DEFAULT_MEDIA = ROOT / "media"

DERIVED_SUFFIXES = ("_1024.webp", "_256.webp")


def stem_of(name: str) -> str:
    for suffix in DERIVED_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(name).stem


def visible_stems(db_path: Path) -> set[str]:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        rows = con.execute(
            """
            select i.path, i.thumb_path
            from images i
            join items it on it.id = i.item_id
            where it.deleted_at is null
            """
        ).fetchall()
    finally:
        con.close()

    stems: set[str] = set()
    for path, thumb in rows:
        for rel in (path, thumb):
            if rel:
                stems.add(stem_of(Path(rel).name))
    return stems


def scan(directory: Path, stems: set[str]) -> tuple[list[Path], int, int]:
    if not directory.exists():
        return [], 0, 0
    orphans: list[Path] = []
    total = 0
    total_bytes = 0
    for path in directory.iterdir():
        if not path.is_file():
            continue
        total += 1
        total_bytes += path.stat().st_size
        if stem_of(path.name) not in stems:
            orphans.append(path)
    return orphans, total, total_bytes


def mb(size: int) -> float:
    return size / (1024 * 1024)


def main() -> int:
    parser = argparse.ArgumentParser(description="清理未引用的媒体文件（默认 dry-run）")
    parser.add_argument("--apply", action="store_true", help="真的删除（默认只统计）")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--media", default=str(DEFAULT_MEDIA))
    args = parser.parse_args()

    media = Path(args.media)
    stems = visible_stems(Path(args.db))

    orig_orphans, orig_total, _ = scan(media / "originals", stems)
    deriv_orphans, deriv_total, _ = scan(media / "derived", stems)
    tmp_dir = media / "tmp"
    tmp_files = [p for p in tmp_dir.iterdir() if p.is_file()] if tmp_dir.exists() else []

    orphans = orig_orphans + deriv_orphans + tmp_files
    orphan_bytes = sum(p.stat().st_size for p in orphans)

    print(f"可见单品涉及的图 stem：{len(stems)} 个")
    print(f"originals：共 {orig_total}，孤儿 {len(orig_orphans)}")
    print(f"derived：  共 {deriv_total}，孤儿 {len(deriv_orphans)}")
    print(f"tmp：      共 {len(tmp_files)}（启动时本来也会清）")
    print(
        f"将删除 originals {len(orig_orphans)} 个 / derived {len(deriv_orphans)} 个"
        f" / 合计 {mb(orphan_bytes):.1f} MB"
    )

    if not args.apply:
        print("dry-run：没有删除任何文件，加 --apply 才执行")
        return 0

    removed = 0
    for path in orphans:
        try:
            path.unlink()
            removed += 1
        except OSError as exc:
            print(f"删除失败 {path.name}：{exc}", file=sys.stderr)

    print(f"已删除 {removed} 个文件，释放 {mb(orphan_bytes):.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
