"""数据库引擎、会话与迁移入口。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_settings.ensure_dirs()

engine = create_engine(
    _settings.db_url,
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def alembic_config() -> Config:
    """库地址只在 app.config 维护一处；ini 里留空，由 env.py 回退取用。"""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def run_migrations() -> None:
    """启动时把库升到 head；新库会自动建到这里的所有表。"""
    command.upgrade(alembic_config(), "head")
