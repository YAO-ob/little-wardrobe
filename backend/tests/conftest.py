"""测试环境：把数据与媒体目录指到仓库内临时目录，避免污染本地库。"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT.parent / ".tmp" / "pytest-media"
DATA_DIR = ROOT.parent / ".tmp" / "pytest-data"
CASE_ROOT = ROOT.parent / ".tmp" / "pytest-cases"

for path in (DATA_DIR, TEST_DIR, CASE_ROOT):
    path.mkdir(parents=True, exist_ok=True)

# 测试库每次从零建，顺便验证 alembic 能从空库升到 head
for suffix in ("", "-wal", "-shm"):
    Path(str(DATA_DIR / "wardrobe.db") + suffix).unlink(missing_ok=True)

os.environ["EW_DATA_DIR"] = str(DATA_DIR)
os.environ["EW_MEDIA_DIR"] = str(TEST_DIR)

from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def workdir() -> Path:
    """替代 tmp_path：本机沙箱下 pytest 的 0700 临时目录不可写。"""
    path = CASE_ROOT / f"case-{uuid.uuid4().hex[:8]}"
    os.makedirs(path, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_media():
    yield
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR, ignore_errors=True)
    TEST_DIR.mkdir(parents=True, exist_ok=True)
