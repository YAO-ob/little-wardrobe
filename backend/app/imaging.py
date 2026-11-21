"""图片处理：EXIF 方向校正 → 剥离元数据（含 GPS）→ 两档 WebP。"""

from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageOps
from pillow_heif import register_heif_opener

# iPhone 直出是 HEIC；注册后 Pillow 才能打开。失败就按 UnsupportedImage 走 415。
register_heif_opener()

DERIVED_WIDTH = 1024
THUMB_WIDTH = 256
WEBP_QUALITY = 82
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".heic", ".heif"}


class UnsupportedImage(Exception):
    """文件不是可解码的图片。"""


def new_stem() -> str:
    return uuid.uuid4().hex


def _open_clean(src: Path) -> PILImage.Image:
    """按 EXIF 方向摆正，并重建图像以丢弃全部元数据。"""
    try:
        with PILImage.open(src) as raw:
            raw.load()
            upright = ImageOps.exif_transpose(raw)
            rgb = upright.convert("RGB")
            # 重建一张新图：pixel 拷贝，info/exif/icc 全部不带走
            clean = PILImage.new("RGB", rgb.size)
            clean.paste(rgb)
            return clean
    except UnsupportedImage:
        raise
    except Exception as exc:  # noqa: BLE001
        raise UnsupportedImage(str(exc)) from exc


def _fit_width(img: PILImage.Image, width: int) -> PILImage.Image:
    if img.width <= width:
        return img.copy()
    height = max(1, round(img.height * width / img.width))
    return img.resize((width, height), PILImage.LANCZOS)


def _save_webp(img: PILImage.Image, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "WEBP", quality=WEBP_QUALITY, method=6)


def process_upload(src: Path, derived_dir: Path, stem: str) -> dict[str, object]:
    """生成展示档与缩略图，返回它们的相对路径与尺寸。"""
    clean = _open_clean(src)

    display = _fit_width(clean, DERIVED_WIDTH)
    thumb = _fit_width(clean, THUMB_WIDTH)

    display_path = derived_dir / f"{stem}_{DERIVED_WIDTH}.webp"
    thumb_path = derived_dir / f"{stem}_{THUMB_WIDTH}.webp"
    _save_webp(display, display_path)
    _save_webp(thumb, thumb_path)

    return {
        "display": display_path,
        "thumb": thumb_path,
        "width": display.width,
        "height": display.height,
    }
