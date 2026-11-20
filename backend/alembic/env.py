"""Alembic 环境：迁移目标 = 应用里的 Base.metadata。

SQLite 的 ALTER 能力很弱，所以统一开 render_as_batch=True，
以后改列（加约束、改类型）才能 autogenerate 出可用脚本。
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import models  # noqa: F401,E402  确保所有表注册进 metadata
from app.config import get_settings  # noqa: E402
from app.db import Base  # noqa: E402

config = context.config
target_metadata = Base.metadata


def get_url() -> str:
    """ini 里显式给了就用它；否则用应用的数据库地址。"""
    return config.get_main_option("sqlalchemy.url") or get_settings().db_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
