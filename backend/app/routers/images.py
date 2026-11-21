"""图片上传：先落 media/tmp/，建单品成功后再搬到正式目录。

转码仍然留在上传这一步（不能挪到保存链路上拖慢录入），
所以这里一次生成原图 + 1024 + 256 三份文件，全部放在 tmp 下。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..imaging import ALLOWED_SUFFIXES, UnsupportedImage, new_stem, process_upload
from ..models import Image
from ..schemas import ImageOut, image_to_out

router = APIRouter()


@router.post("", response_model=ImageOut, status_code=201)
async def upload_image(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> ImageOut:
    settings = get_settings()
    settings.ensure_dirs()

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的格式 {suffix or '(空)'}，请用 jpg / png / webp",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="图片过大，请压缩到 12MB 以内")

    tmp_dir = settings.tmp_dir
    stem = new_stem()
    original = tmp_dir / f"{stem}{suffix}"
    original.write_bytes(raw)

    try:
        result = process_upload(original, tmp_dir, stem)
    except UnsupportedImage as exc:
        original.unlink(missing_ok=True)
        raise HTTPException(
            status_code=415, detail="图片无法解析，格式可能不受支持"
        ) from exc

    display: Path = result["display"]  # type: ignore[assignment]
    thumb: Path = result["thumb"]  # type: ignore[assignment]

    image = Image(
        path=display.relative_to(settings.media_dir).as_posix(),
        thumb_path=thumb.relative_to(settings.media_dir).as_posix(),
        width=int(result["width"]),  # type: ignore[arg-type]
        height=int(result["height"]),  # type: ignore[arg-type]
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image_to_out(image)


@router.delete("/{image_id}", status_code=204)
def delete_staged_image(image_id: int, db: Session = Depends(get_db)) -> None:
    image = db.get(Image, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="图片不存在")
    if image.item_id is not None:
        raise HTTPException(status_code=409, detail="已归属单品的图片请走单品接口")
    settings = get_settings()
    for rel in (image.path, image.thumb_path):
        if rel:
            (settings.media_dir / rel).unlink(missing_ok=True)
    db.delete(image)
    db.commit()
