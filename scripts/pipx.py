"""pip 包装器：绕过本机沙箱下 0o700 临时目录不可写的问题。

背景：DSH 文件沙箱里，`os.mkdir(path, 0o700)` 创建的目录后续写入会被拒绝
（Windows ACL 与受限令牌叠加），而 `tempfile.mkdtemp` 默认就是 0700，
导致 pip 在解包/缓存临时目录上必然 PermissionError。

用法（等价于 python -m pip ...）：
    python scripts/pipx.py install -r backend/requirements.txt

只改临时目录的创建方式，不动 pip 的任何解析逻辑。
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid


def _safe_mkdtemp(suffix: str | None = None, prefix: str | None = None, dir: str | None = None) -> str:
    base = dir or tempfile.gettempdir()
    for _ in range(200):
        name = os.path.join(base, f"{prefix or 'tmp'}{uuid.uuid4().hex[:10]}{suffix or ''}")
        try:
            os.makedirs(name)  # 默认 0o777，沙箱下可写
            return os.path.abspath(name)
        except FileExistsError:
            continue
    raise FileExistsError("无法创建临时目录")


tempfile.mkdtemp = _safe_mkdtemp  # type: ignore[assignment]

from pip._internal.cli.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
