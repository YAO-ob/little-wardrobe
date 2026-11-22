"""occasion 单值改多值（JSON 数组）

Revision ID: b8e3f1a2c7d4
Revises: c43a9b2d4cb9
Create Date: 2026-11-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e3f1a2c7d4"
down_revision: Union[str, Sequence[str], None] = "c43a9b2d4cb9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 存量单值转 JSON 数组字符串："work" -> '["work"]'；空串 / NULL -> NULL
    #    场合值是固定枚举（casual/work/sport/formal），不含引号，直接拼接安全。
    op.execute("UPDATE items SET occasion = NULL WHERE occasion = '' OR occasion IS NULL")
    op.execute(
        "UPDATE items SET occasion = '[\"' || occasion || '\"]' "
        "WHERE occasion IS NOT NULL AND occasion NOT LIKE '[%'"
    )
    # 2) JSON 文本上的等值索引已无意义（筛选走 LIKE 包含匹配），删掉；再把列改宽成 Text
    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_index(batch_op.f("ix_items_occasion"))
        batch_op.alter_column(
            "occasion",
            existing_type=sa.String(length=16),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("items") as batch_op:
        batch_op.alter_column(
            "occasion",
            existing_type=sa.Text(),
            type_=sa.String(length=16),
            existing_nullable=True,
        )
        batch_op.create_index(batch_op.f("ix_items_occasion"), ["occasion"], unique=False)
    # 数组取第一个元素转回单值；空数组 -> NULL
    op.execute("UPDATE items SET occasion = NULL WHERE occasion = '[]' OR occasion IS NULL")
    op.execute(
        "UPDATE items SET occasion = json_extract(occasion, '$[0]') "
        "WHERE occasion LIKE '[%' AND json_extract(occasion, '$[0]') IS NOT NULL"
    )
