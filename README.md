# 电子衣柜

记录自己的衣服，按今天的天气和场合给出搭配的 Web 应用。当前进度：**W1 竖切跑通（R1–R4）**，推荐链路（W2）尚未开始。

## 现在能做什么

- **极速录入**：拍照 / 一次多选连拍 → 品类（1–6）→ 厚薄（Q/W/E）→ Enter 保存，3 次点击一件，队列自动推进
- **图库**：九宫格缩略图，按品类 / 场合 / 关键字 / 「信息不全」筛选
- **图片处理**：上传即校正 EXIF 方向、剥离全部元数据（含 GPS），生成 1024 展示档与 256 缩略图两档 WebP
- **数据**：SQLite（WAL）+ SQLAlchemy 2.1，`data/wardrobe.db`

## 一键启动

```powershell
.\dev.cmd
```

- 后端 http://127.0.0.1:8000 （`/healthz`、`/docs`）
- 前端 http://127.0.0.1:5173
- 只起后端：`.\dev.cmd -ApiOnly`
- 热重载：`.\dev.cmd -Reload`（当前沙箱里 `--reload` 会因为拿不到命名管道而崩，普通机器可用）

首次拉代码后装依赖（本机没有系统 Python/Node，用 DSH 内置运行时，见 DECISIONS.md 第 1 节）：

```powershell
$py = "C:\Users\YAOob\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$node = "C:\Users\YAOob\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
$pnpm = "C:\Users\YAOob\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.mjs"

& $py scripts\pipx.py install --target backend\.pyenv -r backend\requirements-dev.txt
& $node $pnpm --dir frontend install
```

`scripts\pipx.py` 是 pip 的包装器（绕开沙箱下 0700 临时目录不可写的坑），换到正常机器直接 `pip install` 即可。

## 目录结构

```
backend/
  alembic/         迁移脚本（versions/ 里是历史）
  alembic.ini      连接地址留空，由 app.config 兜底
  app/
    main.py        FastAPI 应用、启动时迁移、/healthz、/media 静态目录
    config.py      pydantic-settings，EW_ 前缀环境变量
    db.py          引擎 + 会话 + PRAGMA + run_migrations()
    models.py      items / images
    schemas.py     请求响应模型
    imaging.py     EXIF 摆正 → 剥元数据 → 两档 WebP
    routers/       items.py、images.py
  tests/           15 个用例：接口 + 图片管线 + 两阶段上传
frontend/
  src/core/        纯逻辑：类型、API client、文案、快捷键与守卫（有单测）
  src/adapters/    storage/upload/image/toast，平台差异只在这层
  src/ui/          App、录入页、图库页、Toast
scripts/           dev.ps1、pipx.py、smoke_r1.py、seed_30.py
scripts/manual/    需要真浏览器的手工脚本（当前有一个未验证的）
```

分层约束：`core/` 不 import `window` / `document` / `localStorage` / `react-dom`，保证以后迁小程序时逻辑层可复用。

## 数据库迁移

启动时自动 `alembic upgrade head`，所以正常情况下不用管。新增一次改动：

```powershell
cd backend
python -m alembic revision --autogenerate -m "add outfit tables"
python -m alembic upgrade head
```

- `env.py` 里开了 `render_as_batch=True`，SQLite 的 ALTER 走「建新表→拷数据」，以后改列不用手写。
- baseline 只有 `items`、`images`（`9f64bc6d95b5`），现有库已经 `stamp head`。
- 不要对着业务库跑 autogenerate，先指到空库（`EW_DATA_DIR=...`）再生成，否则脚本里全是 drop/alter。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 存活探针 |
| POST | `/api/images` | multipart 上传。转码在上传时完成，文件先落 `media/tmp/`，返回 `{id, url, thumb_url, width, height}`（此时 url 指向 `/media/tmp/...`） |
| DELETE | `/api/images/{id}` | 删除尚未归属单品的暂存图 |
| POST | `/api/items` | 建单品。带 `image_ids` 时把 tmp 里的原图搬进 `originals/`、两档派生图搬进 `derived/`，并改写 `path` |
| GET | `/api/items` | 列表，支持 `category`（可重复）、`occasion`、`q`、`incomplete`、`limit`、`offset` |
| GET | `/api/items/{id}` | 单品详情 |
| PATCH | `/api/items/{id}` | 局部更新（补颜色/品牌/价格等选填字段） |
| DELETE | `/api/items/{id}` | 软删除 |
| GET | `/api/weather?city=杭州` | 今天的日预报（Open-Meteo）。不传 city 用杭州；城市不在内置表里 → 400；上游失败有旧数据 → 200 + `stale=true`；无旧数据 → 502 |

图片两阶段的约定：上传成功不等于图已入库；只有单品保存成功才会搬出 tmp。启动时会清空 `media/tmp/`，所以半途而废的上传不会留下孤儿图。

## W1 验收

| 标准 | 状态 | 证据 |
|---|---|---|
| 30 件衣服 15 分钟内录完 | 通过（机器侧） | `scripts/seed_30.py`：30 件保存耗时 6.5s，216ms/件；叠加人手 10s/件 ≈ 5.7 分钟 |
| 刷新不丢 | 通过 | SQLite WAL 落盘 `data/wardrobe.db` |
| 缩略图 <100KB | 通过 | `backend/tests/test_imaging.py::test_two_derivatives_and_size` |

手工验收（3 步）：

1. `.\dev.cmd`，打开 http://127.0.0.1:5173
2. 「录入」页选图 → 按 `1` 选上衣 → 按 `Enter` 保存，页面提示已存 1 件
3. 切到「图库」，能看到刚录的衣服缩略图；筛「信息不全」只剩没填颜色的

## 测试

```powershell
# 后端：接口 + 图片管线 + 两阶段上传，15 条
$env:PYTHONPATH = "$PWD\backend\.pyenv;$PWD\backend"
python -m pytest backend\tests -q

# 前端：键盘守卫与快捷键映射，19 条（core/ 改逻辑必须过这关）
node frontend\node_modules\vitest\vitest.mjs run --root frontend
# 或 cd frontend && pnpm test
```

真浏览器按键连录脚本（需要能启动 Edge/Chrome 的环境，本机沙箱跑不了，且**从未验证过**）：

```powershell
node scripts\manual\e2e-r2-keyboard.mjs
```

## 已知缺口（按优先级）

0. **R2 键盘连录尚未在真浏览器验证**：守卫与映射有 19 条单测镇着，但「按 10 次键连录 10 件」需要人工或换台机器跑 `scripts/manual/e2e-r2-keyboard.mjs`
1. **没有 CI / Docker**：W4 的事，但仓库里已留 `.env.example`
2. **HEIC 不支持**：iPhone 直出照片需先转 jpg，或加 `pillow-heif`
3. **单品详情/编辑/删除没有 UI**：接口都在，页面只做了录入与图库
4. **无鉴权**：仅本机使用，公开部署前必须加访问控制
5. **推荐链路（W2）未开始**：天气、规则候选、模型层、缓存限流都还没有
6. **孤儿图只在启动时清**：应用长跑期间，用户传了图不保存会一直躺在 `media/tmp/`，重启才清

## 数据与隐私

- 原图留在 `media/originals/`，生成图在 `media/derived/`，未完成的暂存在 `media/tmp/`（启动清空），三者都不进版本库
- 上传时剥离 EXIF（含 GPS），落盘文件不含拍摄地点

## 第三方

- 天气数据来自 [Open-Meteo](https://open-meteo.com/)（免 key，**非商用**，需署名）。后端代取、按「坐标+日期」缓存 2 小时，前端不直连。
- 上游不可达时会退回上一次成功结果并标 `stale=true`，不会把错误伪装成正常数据。
