"""小柜子后端：应用配置。"""

import shutil
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 仓库根目录（backend/ 的上一级）
ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="EW_", extra="ignore")

    app_name: str = "小柜子"
    data_dir: Path = ROOT_DIR / "data"
    media_dir: Path = ROOT_DIR / "media"
    database_url: str = ""  # 留空则用 sqlite:///data/wardrobe.db
    max_upload_bytes: int = 12 * 1024 * 1024  # 单张原图上限

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = (self.data_dir / "wardrobe.db").as_posix()
        return f"sqlite:///{db_path}"

    @property
    def originals_dir(self) -> Path:
        return self.media_dir / "originals"

    @property
    def derived_dir(self) -> Path:
        return self.media_dir / "derived"

    @property
    def tmp_dir(self) -> Path:
        """暂存区：上传先落这里，建单品成功后才搬到正式目录。"""
        return self.media_dir / "tmp"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.originals_dir, self.derived_dir, self.tmp_dir):
            path.mkdir(parents=True, exist_ok=True)

    def clear_tmp(self) -> None:
        """启动时清空暂存区：里面的东西都是没走完流程的孤儿。"""
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
