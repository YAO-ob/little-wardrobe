"""数据模型：单品与图片。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(32))
    color_family: Mapped[str | None] = mapped_column(String(16))
    color_hex: Mapped[str | None] = mapped_column(String(9))
    season: Mapped[str | None] = mapped_column(Text)  # JSON 数组字符串
    occasion: Mapped[str | None] = mapped_column(String(16), index=True)
    warmth: Mapped[int | None] = mapped_column(Integer)  # 1 薄 2 中 3 厚
    formality: Mapped[int | None] = mapped_column(Integer)  # 1-5
    layer: Mapped[str | None] = mapped_column(String(8))  # inner / mid / outer
    material: Mapped[str | None] = mapped_column(String(64))
    brand: Mapped[str | None] = mapped_column(String(64))
    price: Mapped[float | None] = mapped_column(Float)
    purchased_at: Mapped[str | None] = mapped_column(String(10))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)
    updated_at: Mapped[str] = mapped_column(String(32), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[str | None] = mapped_column(String(32))

    images: Mapped[list[Image]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by=lambda: (Image.is_primary.desc(), Image.id.asc()),
    )


Index("idx_items_cat", Item.category, Item.deleted_at)


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 暂存阶段允许为空：先传图、再建单品，见 DECISIONS.md
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)  # 相对 media/ 的路径
    thumb_path: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)

    item: Mapped[Item | None] = relationship(back_populates="images")
