"""图片管线测试：方向校正、元数据剥离、两档尺寸、体积上限。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.imaging import DERIVED_WIDTH, THUMB_WIDTH, UnsupportedImage, process_upload


def _make_rotated_jpeg(path: Path, width: int = 1200, height: int = 1600) -> None:
    img = Image.new("RGB", (width, height), (100, 140, 200))
    exif = Image.Exif()
    exif[0x0112] = 6  # 相机竖拍：需要转 90 度才是正方向
    exif[0x010F] = "TESTCAM"
    img.save(path, "JPEG", quality=90, exif=exif.tobytes())


def test_exif_orientation_applied(workdir: Path) -> None:
    src = workdir / "rotated.jpg"
    _make_rotated_jpeg(src)

    result = process_upload(src, workdir, "stem")
    display = Image.open(result["display"])

    # 原图 1200x1600 竖拍，orientation=6 摆正后应是横的
    assert display.width > display.height
    assert result["width"] == DERIVED_WIDTH


def test_metadata_stripped(workdir: Path) -> None:
    src = workdir / "with_exif.jpg"
    _make_rotated_jpeg(src)
    assert Image.open(src).getexif().get(0x0112) == 6

    result = process_upload(src, workdir, "stem")
    out = Image.open(result["display"])

    assert not out.getexif()
    for key in ("exif", "icc_profile", "photoshop"):
        assert key not in out.info


def test_two_derivatives_and_size(workdir: Path) -> None:
    src = workdir / "big.jpg"
    Image.new("RGB", (2400, 3000), (30, 30, 30)).save(src, "JPEG")

    result = process_upload(src, workdir, "stem")
    display = Path(result["display"])
    thumb = Path(result["thumb"])

    assert display.exists() and thumb.exists()
    assert display.suffix == ".webp" and thumb.suffix == ".webp"
    assert Image.open(display).width == DERIVED_WIDTH
    assert Image.open(thumb).width == THUMB_WIDTH
    assert thumb.stat().st_size < 100 * 1024  # W1 验收：缩略图 <100KB


def test_broken_file_raises(workdir: Path) -> None:
    src = workdir / "broken.jpg"
    src.write_bytes(b"not an image")

    try:
        process_upload(src, workdir, "stem")
    except UnsupportedImage:
        return
    raise AssertionError("坏文件应该抛 UnsupportedImage")
