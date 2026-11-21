# 电子衣柜

<!-- 仓库建好后，把下面这行里的 OWNER/REPO 换成实际地址并取消注释；
     现在留空/注释掉是为了避免写死一个不存在的仓库名导致徽标 404。
[![CI](https://img.shields.io/github/actions/workflow/status/OWNER/REPO/ci.yml?branch=main&label=CI)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
-->

记录自己的衣服，按当天天气和场合给出搭配建议的单用户 Web 应用。

**TL;DR**

- A single-user wardrobe app that turns today's weather + an occasion into three outfit recommendations.
- Stack: React + Vite + TypeScript + Tailwind · FastAPI + SQLite (WAL) + SQLAlchemy 2 + Alembic · Open-Meteo · any OpenAI-compatible LLM (BYOK).
- Highlights: closed-set candidate selection with hard validation and one repair retry, deterministic rule-based fallback, latency/token metrics API, and a no-Docker two-command local run.

## 截图

三个页面的截图待补，目录已建好（除占位文件外为空，不放假图）：

| 页面 | 文件 |
|---|---|
| 录入页 | `docs/screenshots/record.png` |
| 图库 | `docs/screenshots/gallery.png` |
| 搭配页 | `docs/screenshots/outfit.png` |

生成方式：按下方「本地运行」启动后，依次打开「录入」「图库」「搭配」三个标签，各截一张 750px 宽的图，按上表命名放进 `docs/screenshots/`。

完整演示流程与口播要点见 [docs/DEMO.md](docs/DEMO.md)。

## 现在能做什么

- **极速录入**：选图 → 品类 → 厚薄 → 场合，三次点击一件；支持连拍队列与键盘快捷键（`1-6` / `Q W E` / `Enter`）。
- **图库与筛选**：九宫格缩略图，按品类、场合、关键字、「信息不全」筛选。
- **删除**：卡片右上角删除，按钮内二次确认，软删除可恢复（数据库层面）。
- **天气 + 3 套规则推荐**：不接模型也能出三套搭配，每套带一句中文理由。
- **AI 精选（BYOK）**：在页面填入自己的 key，让模型从规则候选里挑一套；失败自动降级并说明原因。
- **保存搭配**：「就穿这套」把当天这套写进 `outfits`，`wear_log` 视图可直接查穿着记录。

## 技术栈与架构

| 层 | 选型 |
|---|---|
| 前端 | React + Vite + TypeScript + Tailwind，纯 SPA，分 `core` / `adapters` / `ui` 三层，`core` 不碰 `window` |
| 后端 | FastAPI + SQLite（WAL）+ SQLAlchemy 2 + Alembic，图片处理用 Pillow |
| 天气 | Open-Meteo，双模型：CMA 出温度体感、best_match 出降水概率/UV/天气码 |
| 模型层 | OpenAI 兼容协议，key 由使用者自带（BYOK），可切换 base_url 与 model |

请求链路：

```
请求 → 天气（缓存 2h）→ 规则候选（10–15 件）→ 模型只选 id
     → 四条硬校验 → 失败回灌错误重出一次 → 仍失败 → 规则结果兜底
```

## 本地运行

前置：Python 3.12+、Node 20+、pnpm。

```bash
# 后端
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
cd backend && alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

```bash
# 前端（另开一个终端）
cd frontend
pnpm install
pnpm dev
```

打开 http://127.0.0.1:5173 即可；API 文档在 http://127.0.0.1:8000/docs。

## 测试

```bash
pytest backend/tests -q              # 后端 146 条
pnpm --dir frontend test             # 前端 35 条
pnpm --dir frontend typecheck
```

模型与天气相关的测试全部用 mock，不需要真实 key、不需要联网。

## 第一次运行没有数据

先启动后端，再执行：

```bash
python scripts/seed_30.py     # 生成 30 件演示单品（色块图，用于看效果）
```

脚本会通过 HTTP 调后端，因此后端必须已在 `127.0.0.1:8000` 运行。它生成的是纯色块图片，不是真实照片。

## 推荐是怎么工作的

- 规则先按体感温度分档（薄/中/厚）、场合、厚薄差与正式度打分，每类取前几件组成 10–15 件的候选池。
- 模型只在这个池子里挑 `item_id`，不允许自由生成单品。
- 后端做四条硬校验：id 必须在池内、件数 3–6、不许重复、品类覆盖（上装或裙装、下装或裙装、鞋，冷天还要外套）。
- 校验失败时把「哪些 id 非法、缺了哪类」回灌给模型重出一次；第二次仍失败就降级成规则推荐，接口始终 200。
- 一句话：**防幻觉靠候选集闭合校验，不靠 prompt 里写「不许编造」。**

## 可观测

`GET /api/metrics?days=30`（1–90 天）返回调用量、成功率、缓存命中、降级原因分布、token 消耗与延迟分位；`model_latency_ms` 只统计真实模型调用，`latency_ms` 是请求级耗时。

当前库里的真实数据（近 30 天）：

| 指标 | 值 |
|---|---|
| `total_calls` | 52 |
| `llm_success` | 12 |
| `fallbacks` | 36（`no_key` 23 · `missing_category` 9 · `rate_limited` 3 · `http_401` 1） |
| `cache_hits` | 4 |
| `model_latency_ms` | p50 763 ms · p95 1078 ms |
| `tokens` | prompt 4384 · completion 560 |

## 配置

全部是可选的 `EW_` 前缀环境变量，示例见 `.env.example`。

| 变量 | 默认 | 说明 |
|---|---|---|
| `EW_DATA_DIR` | `./data` | 数据库与运行数据目录 |
| `EW_MEDIA_DIR` | `./media` | 原图与派生图目录 |
| `EW_DATABASE_URL` | 由 `EW_DATA_DIR` 推导 | 需要直接指定数据库连接串时用 |
| `EW_LLM_KEY` | 空 | 模型 key；不设也能在页面里填（BYOK），都不设则只有规则推荐 |
| `EW_LLM_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容服务的地址 |
| `EW_LLM_MODEL` | `deepseek-chat` | 模型名 |
| `EW_LLM_MAX_TOKENS` | `800` | 单次生成上限（推理模型要给够预算） |
| `EW_LLM_CACHE_TTL` | `1800` | 推荐结果缓存秒数 |
| `EW_LLM_RATE_LIMIT_PER_MIN` | `10` | 每个客户端每分钟可调模型的次数 |

**都不设置也能跑，只是没有 AI 推荐。**

## 数据与隐私

- 原图存本地 `media/originals/`，派生图在 `media/derived/`，都不进版本库。
- 上传时按 EXIF 摆正方向，并剥离 EXIF/ICC 元数据（含 GPS），落盘文件不含拍摄地点。
- 模型 key 只存在浏览器 `localStorage`，请求时通过 `X-LLM-Key` 请求头传给自己的后端。
- 后端不落库、不写日志；日志里只有 key 的 sha256 前 8 位指纹。

## 已知限制

- 无鉴权、无登录：设计为单用户本地运行，公开部署前必须加访问控制。
- 推荐结果缓存与限流都是**进程内**的：多 worker 或多实例时各算各的。
- 图片暂存区只在启动时清理，长跑期间未完成的图片会留在 `media/tmp/`。
- 删除是软删除，没有回收站与撤销入口；搭配也没有历史页。
- 不支持 HEIC/HEIF（需要额外解码库）。
- 天气没有持久化快照，进程重启后冷启动撞上上游不可用会直接 502。
- Docker 与部署脚本尚未提供（CI 已配置：`.github/workflows/ci.yml`）。

面试口径与能力边界见 [docs/INTERVIEW.md](docs/INTERVIEW.md)。

## 第三方

- 天气数据来自 [Open-Meteo](https://open-meteo.com/)，免 key、**仅限非商用**，本项目在页面与文档中署名。
- 本项目代码以 MIT 许可证发布，详见 `LICENSE`。

## 目录结构

```
电子衣柜/
├── backend/
│   ├── alembic/          # 迁移脚本（baseline → outfits → llm_metrics）
│   ├── app/routers/      # items / images / outfits / recommend / weather / metrics
│   ├── app/rules.py      # 纯规则：分档、打分、组套
│   ├── app/llm*.py       # 模型客户端、候选校验、结果缓存
│   ├── app/weather.py    # 双模型取数 + 超时重试
│   └── tests/            # 接口 / 规则 / 指标测试
├── frontend/src/
│   ├── core/             # 纯逻辑：类型、API client、文案
│   ├── adapters/         # 平台差异：上传、预览、toast、key 存取
│   └── ui/               # 页面：录入 / 图库 / 搭配
├── scripts/              # seed_30.py
├── docs/screenshots/     # 截图（待补）
└── DECISIONS.md          # 每个技术选择的理由
```

> 本仓库的开发环境使用了 DSH 内置的 Python 与 Node 运行时（路径与系统安装不同），相关细节与踩坑记录见 [DECISIONS.md](DECISIONS.md)。
