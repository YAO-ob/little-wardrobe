"""数据模型：单品与图片。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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


class Outfit(Base):
    """一次「今天穿这套」。"""

    __tablename__ = "outfits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worn_on: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    # 当天天气快照（温度区间/体感/降水），不存就永远解释不了"当时为什么这么配"
    weather_json: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow)
    deleted_at: Mapped[str | None] = mapped_column(String(32))

    items: Mapped[list[OutfitItem]] = relationship(
        back_populates="outfit",
        cascade="all, delete-orphan",
    )


class OutfitItem(Base):
    """搭配里的每一件（同一次搭配不许同一件出现两次）。"""

    __tablename__ = "outfit_items"
    __table_args__ = (UniqueConstraint("outfit_id", "item_id", name="uq_outfit_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    outfit_id: Mapped[int] = mapped_column(
        ForeignKey("outfits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    layer: Mapped[str | None] = mapped_column(String(8))  # inner / mid / outer

    outfit: Mapped[Outfit] = relationship(back_populates="items")


class WeatherSnapshotRow(Base):
    """最后一次成功的天气快照：上游挂了就拿它兜底，重启也不丢。"""

    __tablename__ = "weather_snapshots"

    city_name: Mapped[str] = mapped_column(String(32), primary_key=True)
    observed_at: Mapped[str] = mapped_column(String(32), nullable=False)  # 数据对应的日期
    fetched_at: Mapped[str] = mapped_column(String(32), nullable=False)  # 抓取时刻（ISO）
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # WeatherSnapshot 的 JSON


class LlmMetric(Base):
    """一次推荐请求的指标。只记 mode=llm 的请求。"""

    __tablename__ = "llm_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(
        String(32), default=utcnow, nullable=False, index=True
    )
    mode: Mapped[str | None] = mapped_column(String(8))  # rules / llm
    source: Mapped[str | None] = mapped_column(String(8))  # llm / rules
    cached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(24))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model: Mapped[str | None] = mapped_column(String(48))
    tokens_prompt: Mapped[int | None] = mapped_column(Integer)
    tokens_completion: Mapped[int | None] = mapped_column(Integer)
    is_byok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
