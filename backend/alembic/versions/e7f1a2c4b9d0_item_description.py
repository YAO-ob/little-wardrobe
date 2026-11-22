"""add description to items

Revision ID: e7f1a2c4b9d0
Revises: b8e3f1a2c7d4
Create Date: 2026-11-22 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f1a2c4b9d0'
down_revision: Union[str, Sequence[str], None] = 'b8e3f1a2c7d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('items', schema=None) as batch_op:
        batch_op.drop_column('description')
