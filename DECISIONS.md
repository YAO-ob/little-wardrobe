# 决策记录

按时间倒序不重要，按「以后会忘、忘了会返工」排序。每条都写清「选了什么 / 为什么 / 什么时候该推翻」。

---

## 1. 运行环境：全部用 DSH 内置运行时，不装系统级 Node/Python

本机没有可用系统 Node，Python 只有 Store 占位符。因此：

| 东西 | 位置 |
|---|---|
| Node 24 + pnpm | `C:\Users\YAOob\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin`、`...\pnpm\bin\pnpm.mjs` |
| Python 3.12 | `...\dependencies\python\python.exe` |
| 后端依赖 | `backend\.pyenv`（`pip install --target`），运行时靠 `PYTHONPATH` 注入 |
| 前端依赖 | `frontend\node_modules` |

`scripts/dev.ps1` 里已把这四条写成默认值，可用 `EW_PYTHON` / `EW_NODE_DIR` / `EW_PNPM` 覆盖。
**什么时候改**：换机器或装好系统运行时后，把 dev.ps1 的默认路径换成 `python` / `node` 即可，别的地方不受影响。

## 2. 不用 venv：沙箱下 `ensurepip` 必炸

本机沙箱里 `os.mkdir(path, 0o700)` 建出来的目录，后续写入会被拒绝；而 `tempfile.mkdtemp` 默认就是 0700。
`python -m venv` 会调 `ensurepip`，它把 wheel 解到 mkdtemp 目录 → `PermissionError`。

绕法：装依赖用 `scripts/pipx.py`（把 `tempfile.mkdtemp` 换成 `os.makedirs` 默认权限，其余完全走 pip），装到 `backend\.pyenv`。

```powershell
python scripts\pipx.py install --target backend\.pyenv -r backend\requirements-dev.txt
```

**什么时候改**：离开这个沙箱环境（CI、Docker、别人的机器）就回到标准 `pyproject + venv`。Dockerfile 里不要带 pipx.py。

## 3. 测试替身：`tmp_path` → `workdir` fixture

同一条 0700 限制，pytest 的 `tmp_path` 也建不出可写目录。`backend/tests/conftest.py` 提供 `workdir` fixture，在 `.tmp/pytest-cases/` 下用 `os.makedirs` 建目录并自动清理。
**什么时候改**：环境正常后可换回 `tmp_path`，但保留 `workdir` 也无害。

## 4. 建表：R1 先用 `create_all`，Alembic 后补

`init_db()` 在 lifespan 里跑 `Base.metadata.create_all`，只对「表不存在」生效，不做迁移。
理由：R1 的目标是「十分钟内能看到一件衣服」，迁移工具对单表首版没有收益。

**什么时候必须改**：下一次改字段之前。具体做法——`alembic init`、`target_metadata = Base.metadata`、对着现有库 `alembic stamp head`，之后只走迁移，不再靠 create_all。SQLite 改列有限制，届时要走 batch_alter_table。

## 5. 图片先传后挂：`images.item_id` 允许为空

渲染顺序是「选图 → 上传拿 id → 建单品时把 image_ids 挂上去」，所以图片记录要先于单品存在。
`images.item_id` 因此可空；`POST /api/items` 只接受 `item_id IS NULL` 的图，防止一张图挂两件衣服。

**代价**：如果用户传了图但没保存单品，会留下孤儿图。目前没有清理任务。
**什么时候补**：W2 之前加一个「启动时删掉 24 小时前的孤儿图」的小任务就够，别上定时框架。

## 6. 图片管线：重建图像来剥元数据

`ImageOps.exif_transpose` 摆正 → `convert("RGB")` → `Image.new` + `paste` 重建一张新图 → LANCZOS 缩放到 1024 / 256 → WebP q82。
重建而不是「保存时传 `exif=b""`」的原因：Pillow 的 `info` 里还会带 ICC、exif、photoshop 等键，某些格式会顺手写回文件；重建图 `info` 是空的，测试里直接断言 `not out.getexif()` 就能守住。

**验证**：`backend/tests/test_imaging.py` 覆盖方向校正、元数据清空、两档尺寸、缩略图 <100KB、坏文件报错。

**已知限制**：HEIC/HEIF 不在允许列表里（需要 `pillow-heif`，二期随拍照识别一起做）。

## 7. 筛选放服务端

`GET /api/items` 支持 `category`（可重复）、`occasion`、`q`、`incomplete`，前端只拼 query string。
理由：现在是 30 件，明年可能是 300 件；分页参数本来就在接口里，前端过滤迟早要推倒。
`incomplete` 的判定口径 = `color_family` 为空（颜色是第一个补录项，用它当「信息不全」的代表）。

## 8. 键盘映射

`1`–`6` 品类（与界面按钮顺序一致）、`Q/W/E` 薄/中/厚、`Enter` 保存、`Backspace` 跳过。
监听挂在 `window`，但只要焦点在 `input/textarea/select` 里就直接返回，避免以后加搜索框时打架。

## 9. 图片 Content-Type 自己补

Windows 注册表里 `.webp` 常常没有 MIME 映射，StaticFiles 会返回 `application/octet-stream`。
`app/main.py` 里显式 `mimetypes.add_type("image/webp", ".webp")`。

## 10. 状态管理

TanStack Query 管服务端状态（`['items', filter]` 作 key），录入队列用组件内 `useState`。
`zustand` 已装但没用到——跨页共享状态目前为零，不需要为架构完整性提前引入。

## 11. 工具使用纪律

PowerShell 的 `Get-Content`/`Set-Content` 在这台机器上会按 GBK 读写，把中文 UTF-8 源码写坏（已经踩过一次，把测试文件的注释写成了乱码）。
**结论**：中文源码一律只用 `write` / `edit` 工具改，不用 shell 文本替换。

## 12. 启动脚本：`dev.cmd` 包 `dev.ps1`，且默认不开 `--reload`

本机只有 Windows PowerShell 5.1（没有 `pwsh`），且执行策略是 `RemoteSigned`，直接跑 `.ps1` 会被签名策略拦下。
所以入口是 `dev.cmd`：`powershell.exe -ExecutionPolicy Bypass -File scripts\dev.ps1 %*`。

两个脚本都**故意只写 ASCII**：PS 5.1 会把无 BOM 的 UTF-8 脚本按 GBK 读，中文会破坏解析（已经炸过一次）。

`uvicorn --reload` 在这个沙箱里必崩——它靠 multiprocessing 的命名管道做 watchfiles 通信，`CreateNamedPipe` 被拒。
`dev.ps1` 因此默认不带 `--reload`，需要时用 `-Reload`；正常机器上开着更舒服。

**什么时候改**：换到能签名的机器或 CI，删掉 `dev.cmd` 直接用 `pwsh -File scripts\dev.ps1`。

## 13. 本轮验收数据（W1）

| 项 | 数字 |
|---|---|
| 30 件保存（含上传+建库） | 6.5s，216ms/件 |
| 外推人手 10s/件 | ≈5.7 分钟，目标 15 分钟 |
| 缩略图体积 | 1.5–21KB |
| 展示图体积 | 4–56KB |
| 后端测试 | 12 passed |
| 前端构建 | tsc 无错，dist 265KB JS（gzip 82KB） |
| 经 Vite 代理的浏览器链路 | 上传 201 / 建单品 201 / 图库 200 / 缩略图 200 |

## 14. R2 键盘失效：根因与修法（2026-11-21）

**现象**：鼠标选完图后 `1` / `W` / `Enter` 全部失效，按 Enter 还会再弹一次文件选择框，必须用鼠标点一下页面才恢复。

**根因**：`keydown` 守卫写成了「tagName 是 INPUT 就 return」，把隐藏的 `<input type="file">` 也拦了；而选完文件后焦点正好留在那个 input 上。同时文件输入聚焦时，Enter 是浏览器默认的「打开文件选择框」，`preventDefault` 因为先 return 了根本没执行。

**修法**（三处，都在 `CapturePage.tsx`）：

1. `onChange` 里：`addFiles` 之后 `e.target.blur()`，再把焦点交给外层容器
2. 守卫收窄：新增 `isTextEntry()`，只有 text/search/number/password/email/tel/url/date… 这类「正在打字」的输入才 return；file / button / checkbox / radio 一律放行
3. 外层容器加 `tabIndex={-1}` + ref，blur 之后焦点有地方落

顺手把键盘映射抽到 `src/core/shortcuts.ts`（`isTextEntry` + `resolveShortcut`），`CapturePage` 只负责把动作 dispatch 到状态上。

**验证边界（重要，不许含糊）**：

- 已用 jsdom + vitest 覆盖：焦点守卫的每类 input、键位映射、大小写、未知键放行，共 **19 条断言，全绿**。这层直接锁死了本次的根因（`file input` 必须放行）。
- **没有**在真浏览器里跑过「按 10 次键连录 10 件」。两次尝试都失败：
  - Edge headless 在沙箱里起不来（`crashpad OpenProcess: 拒绝访问`，进程秒退）
  - vitest 引入 @testing-library 后 React 在 pnpm 嵌套目录下出现两份实例（`Invalid hook call`），换 alias/dedupe/inline 都没解决
- 因此「连录 10 件」这一条**仍待人工在浏览器里点**；`scripts/e2e-r2-keyboard.mjs` 是给能起浏览器的环境准备的真按键脚本（CDP 派发 trusted 事件，并统计文件框弹出次数），到那种环境直接 `node scripts/e2e-r2-keyboard.mjs`。

**教训**：上一轮把没执行过的「只按键盘连录」写成了通过。以后验收项必须标注「已执行 / 未执行」，没跑过的不许写结果。

## 15. 前端依赖的两个坑

- `pnpm remove` 掉 testing-library 之后，vitest 报 `Cannot find package 'std-env'`（锁文件与 node_modules 不一致），显式 `pnpm add -D std-env` 才恢复。
- 不要用 `pnpm install --force`：在这台机器上会 `ERR_PNPM_SYMLINK_FAILED: Maximum call stack size exceeded`，只能靠普通 install 修。

## 16. N0a：Alembic baseline + 上传两阶段（2026-11-21）

### 迁移

- baseline `9f64bc6d95b5` 只含 `items`、`images` 和索引。生成方式：把 `EW_DATA_DIR` 指到空目录再 `alembic revision --autogenerate`，**不要**对着业务库生成（否则脚本里全是 drop/alter）。
- 现有库（56 件）用 `alembic stamp head` 接管，不重建、不拷数据。
- `lifespan` 里 `create_all` 换成 `run_migrations()` → `alembic.command.upgrade(head)`；`db.py` 里 `alembic_config()` 只设置 `script_location`。**库地址只有 `app/config.py` 一处**：`alembic.ini` 的 `sqlalchemy.url` 留空，`env.py` 的 `get_url()` 回退到 `get_settings().db_url`，程序内启动时也不覆写。
- `env.py` 开 `render_as_batch=True` + `compare_type=True`：SQLite 改列必须先建临时表再拷数据，这个开关决定以后的 autogenerate 能不能直接用。
- `alembic.ini` 必须保持 **ASCII**：alembic 用系统 locale 读 ini，中文注释在 GBK 控制台下直接 `UnicodeDecodeError`（踩过一次）。

### 上传两阶段

- 上传时一次做完所有转码（转码不能挪到保存链路），三份文件都落在 `media/tmp/`；`images.path` 暂存期就是 `tmp/<stem>_1024.webp`，`thumb_path` 同理，不给 schema 加字段。
- `POST /api/items` 挂图成功后才 `os.replace`：原图 → `originals/`，两档 → `derived/`，同时改写两列路径。**先校验 image_ids 再搬文件**，校验失败不留半搬状态。
- 原图扩展名不固定，搬迁时按 `tmp/<stem>.*` 找并排除同 stem 的派生图，不用往库里存原图路径。
- 启动清空 `media/tmp/`——半途而废的上传本来就没有保存价值。
- **URL 契约不动**：`/media` 是整目录静态挂载，`path` 存 `tmp/xxx.jpg` 时 `media_url()` 照样给出可访问地址，所以 `ImageOut.url / thumb_url` 保持 `str`，前端 `ItemImage` 与既有断言都不改。实测暂存期取 `/media/tmp/...` 返回 200（见验收表），没有拿不到 URL 的情况。真要为空该单独提案，不顺手改契约。

### 验收记录（已执行）

| 项 | 结果 |
|---|---|
| 空库 `alembic upgrade head` | 建出 `alembic_version` / `items` / `images`，version=`9f64bc6d95b5` |
| 现有库 `stamp head` | `items=56`、`images=56` 未变 |
| 上传不建单品 | `(originals, derived, tmp)` = `(57,114,0)` → `(57,114,3)`；暂存期 `/media/tmp/...` 与缩略图均 200 |
| 建单品成功 | → `(58,116,0)`，`/media/derived/...` 200，缩略图 200 |
| 后端测试 | 15 passed |
| 前端 | test 19 passed / typecheck 0 / build 0 |

## 17. 前端测试约定（vitest）

- `frontend/src/core/` 是纯逻辑层，**任何 core 改动必须 `pnpm test` 通过**才能提交；目前覆盖 `shortcuts.ts`（焦点守卫 + 键位映射）19 条。
- 不上 `@testing-library/react`：pnpm 嵌套 node_modules 下 React 会出现两份实例，`Invalid hook call`，且本机沙箱起不了浏览器，组件级渲染测试跑不通。组件行为靠人工点，逻辑行为靠单测。
- vitest 必须用 `pool: 'threads'`：默认 forks 池要 spawn 带管道的子进程，沙箱直接 `EPERM`。

## 18. 第 0 项修补 + N0c 图库删除（2026-11-21）

### 暂存文件丢失要立刻炸

`_promote()` 原来在派生图缺失时 `continue`，结果 `images.path` 还指着 `tmp/...`，接口照样返回一个能打开的 URL，问题要等到下次重启 `clear_tmp` 才露出来。改成抛 `HTTPException(500, "暂存文件丢失，请重新上传")`。

配套两点：

- `_attach_images` 先对**所有**待挂图片做存在性校验，再统一搬迁，避免「搬到一半失败」留下半套文件。
- `create_item` 在挂图阶段异常时 `db.rollback()`，不留下半个单品（原来只靠 session 关闭隐式回滚，不明确）。

### 删除语义（钉死，不扩展）

- `DELETE /api/items/{id}` 只写 `deleted_at`（软删）；**media 文件不动，`images.item_id` 不动**。
- 不做回收站、不做彻底删除、不做批量删、不做撤销。
- 图库卡片右上角一个「删除」，`window.confirm` 确认（不做自定义弹层），成功后 `invalidateQueries(['items'])`，失败走 toast，不静默。
- 显示规则：触屏常显；鼠标设备 hover 卡片或键盘 focus 才出现。用 `index.css` 里一条 `.card-delete` 规则实现，不堆 Tailwind 任意变体（嵌套 `@media` 的兼容性不值得赌）。
- 副作用（有意为之）：软删的单品在库里仍占一行，图片文件永久保留。要回收得另做清理任务，超出本轮范围。

## 19. 图库删除点了没反应：定位与改法（2026-11-21）

### 现象

hover 能看到「删除」，点下去既没有 `window.confirm` 弹窗，也没有任何变化或提示。

### 判定（结论 + 证据 + 没做到的部分）

**没做到**：`elementFromPoint` 那段 DevTools 脚本我没法在这台机器上跑——沙箱里 Edge 起不来（crashpad `OpenProcess: 拒绝访问`），没有浏览器可开。所以「是不是被别的元素盖住」这一条**没有实测**，只能给代码层判断和一条给用户的一步验证法。

**代码层判断**：遮挡的可能性低。

- 删除按钮是 `figure` 内最后一个子元素，`position: absolute`，现在再加了 `z-10` + `pointer-events-auto`；
- 「信息不全」角标原来也在右上，本轮移到了左上，右上只剩这个按钮；
- 卡片里没有其他定位元素，`img` 是 static 流内元素，不会盖住绝对定位的按钮。

**症状与「原生对话框被静默拦截」完全吻合**：`window.confirm` 在两种情况下直接返回 false、不留任何痕迹——用户勾过浏览器「阻止此页面创建更多对话框」，或页面处在没有 `allow-modals` 的 iframe 里。表现就是「点了没反应」。

**一步验证法**（下次遇到时）：打开 DevTools → Network，点第二次「确认删除」。

- 有 `DELETE /api/items/{id}` 请求 → 说明点击命中了，问题在别处；
- 没有请求 → 说明 `confirm` 之前就返回了。

现在这条路径已经不依赖 `confirm`，两种情况下都能走通。

### 改法

1. **去掉 `window.confirm`**，改成按钮内二次确认：第一次点变「确认删除」（红底、`data-armed="true"`，靠 CSS 强制保持可见），第二次点同一张才真删。状态机抽到 `core/deleteConfirm.ts`（`resolveDeleteClick`），有 4 条单测。
2. **状态复原**：切筛选/改搜索词（`useEffect` 依赖 filter）、点卡片以外的地方（容器 `onClick` 里判断 `closest('.card-delete')`）、点别的卡片（切换到那张）都会复位。没有计时器。
3. **命中区硬化**：`z-10`、`pointer-events-auto`、`p-1.5`、`min-h-6 min-w-11`，不再只靠 `text-[10px]` 撑尺寸。
4. **失败必有反馈**：`deleteItem` 抛错走 `toast(err.message)`，成功 `toast('已删除')`，任何分支都不静默。

### 顺带发现：dev server 会喂旧模块

改完代码后我核对 dev server 实际返回的模块，发现它是**旧的**（源码里有 `data-armed`，返回的模块里没有）。原因是这个 vite 实例长时间运行、watcher 早前报过 `EBUSY`。重启 `dev.cmd` 后恢复正常。

**规矩**：改完 UI 先确认 dev server 返回的模块里有新标识（比如 `data-armed`），或者直接重启；否则「改了没生效」会被误判成代码问题。

### 验收状态

| 项 | 状态 |
|---|---|
| 前端单测 | 23 passed（原 19 + 删除状态机 4） |
| typecheck / build | 0 / 0 |
| 产物 CSS 含 `.min-h-6` `.min-w-11` `.z-10` `.pointer-events-auto` `[data-armed='true']` | 已确认 |
| dev server 返回新模块（含 `data-armed`、无 `window.confirm`） | 已确认 |
| 浏览器里真点两下删掉一张 | **未执行**（无浏览器），需人工点 |

## 20. N0b：outfit / outfit_items + wear_log 视图（2026-11-21）

迁移 `cc1bfe59e040`，接在 baseline `9f64bc6d95b5` 之后。本轮**只出表结构与迁移**：不写接口、不写规则、不写推荐。

### 表结构

- `outfits`：`id` / `worn_on`(YYYY-MM-DD，非空) / `weather_json`(可空) / `note` / `created_at` / `deleted_at`（与 items 一致的软删）。
- `outfit_items`：`id` / `outfit_id`(FK→outfits, CASCADE, 索引) / `item_id`(FK→items, CASCADE, 索引) / `layer`(inner|mid|outer, 可空)，`UNIQUE(outfit_id, item_id)` 保证同一次搭配不会出现两件相同的。
- 没有加任何业务字段。`weather_json` 留着是刻意的：不存天气快照，以后就永远解释不了「当时为什么这么配」。

### 口径修正：视图只展平，不聚合

上一轮的设想是「wear_log 视图直接给近 30 天穿着次数」，**作废**。

- 视图只展平：`item_id` / `outfit_id` / `worn_on`，过滤 `o.deleted_at IS NULL`。
- 「近 30 天」是**查询期策略参数**，焊进视图以后想改就得再写一个迁移，不划算。
- 穿着次数仍然在查询时 `COUNT`，**不存冗余计数字段**——第 8 节「避免计数漂移」的前提没变，变的只是聚合发生在哪一层（从视图里挪到查询里）。
- 视图 autogenerate 抓不到，`op.execute` 手写；`downgrade` 必须**先 DROP VIEW 再 drop 两张表**，顺序反了会因依赖报错。

### 验收（已执行）

| 项 | 结果 |
|---|---|
| a) 空库 `upgrade head` | 表：`items` / `images` / `outfits` / `outfit_items` / `alembic_version`；视图：`wear_log` |
| b) `downgrade -1` → `upgrade head` | 降级后两张表与视图都不在；再升级全部回来 |
| c) 插 2 条 outfit_items 后查视图 | `wear_log` 返回 2 行，(`item_id`, `outfit_id`, `worn_on`) 都对 |
| d) 后端测试 | 16 passed，不回退 |
| 真实库 | 启动时自动升到 `cc1bfe59e040`，57 件单品未动，`outfits` 0 行 |

## 21. N1：天气服务（2026-11-21）

### 结构

- `app/data/cities.py`：8 个内置城市（杭州默认 + 上海/北京/广州/深圳/成都/南京/武汉），坐标 3 位小数，全部 `Asia/Shanghai`。不做在线 geocoding：中文城市名在 Open-Meteo geocoding 上召回不稳，查不到就 400，让调用方明确失败。
- `app/weather.py`：取数 + 缓存 + 降级；`app/routers/weather.py` 只做 HTTP 映射。
- 只取今天（`forecast_days=1`），不做多日、不做多时区换算。`date` 由城市时区的本地时间算出，不取上游返回的 `daily.time`（避免跨零点时两边不一致）。

### 缓存

- key = `(round(lat,3), round(lon,3), date)`，TTL 硬编码 2 小时，进程内 dict。
- **不用响应里的坐标**：Open-Meteo 会把坐标吸附到网格（传 30.2741 可能返回 30.263618），拿响应值当 key 会永远 hit 不了。测试里特意让 fixture 的 lat/lon 与请求值不同，就是在守这条。
- 过期的成功结果不删：上游失败时还能拿出来降级。

### 降级语义

| 情况 | 返回 |
|---|---|
| 缓存新鲜 | 200，`cached=true, stale=false`，不打上游 |
| 上游失败 + 有过成功结果 | 200，`cached=true, stale=true`（前端提示「天气可能不是最新」） |
| 上游失败 + 无任何缓存 | 502，`detail.code = weather_upstream_failed` |
| 城市不在表里 | 400，detail 列出可选城市 |

超时 5 秒；连接失败、非 200、JSON 结构异常都折成 `UpstreamError`，不把半截数据带出去。

### 日志

`weather city=… date=… cache=hit|miss|stale elapsed_ms=…`，只记这四个字段，**不打响应体**（否则日志会变成噪音）。降级与失败分别用 warning / error。

### 双模型取数（N1b）

单模型 `best_match` 给出的杭州最低温是 3.1℃，明显低于手机（6℃）；中国气象局的 `cma_grapes_global` 给 6.8℃，更贴合。但 CMA 不提供 `precipitation_probability_max` 和 `uv_index_max`（返回 null），所以一次请求带两个模型：

```
models=cma_grapes_global,best_match
```

响应字段带模型后缀（`temperature_2m_min_cma_grapes_global` 等），取值路由：

| 字段 | 首选 | 回退 |
|---|---|---|
| `t_min` / `t_max` / `feels_min` / `feels_max` | CMA | best_match |
| `wind` | CMA | best_match |
| `precip_prob` / `uv` / `weather_code` | best_match | CMA |

任一字段在首选模型缺失或为 null 才回退；**两个都没有就抛 `UpstreamError`（502）**，不静默填 0——0 是「测得是 0」，null 是「没有这个数据」。

`weather_code` 是 WMO 码，中文映射放 `weather.py` 的 `WMO_TEXT` + `WMO_RANGES` 常量（0 晴 / 1-2 多云 / 3 阴 / 45,48 雾 / 51-57 毛毛雨 / 61-67 雨 / 71-77 雪 / 80-82 阵雨 / 95-99 雷雨 / 其余「未知」）。

`WeatherOut` 因此多了 `weather_code`（int）与 `weather_text`（str）。

**实测（2026-11-21 杭州）**：`t_min=6.8`、`t_max=14.6`、`feels 4.1–11.9`、`precip=0`、`uv=4.45`、`weather_code=0`（晴）、`wind=9.7`。

**副作用提醒**：换了温度源后规则分档会变——同一天从「体感 0.8–13.2（温差 12.4，加打底）」变成「4.1–11.9（温差 7.8，不加打底）」。这是预期行为，规则的阈值没动。

### 更正：不是网络问题，是坐标写反（同一个迁移）

上一版这里写着「上游不可达、TLS 握手超时」，**这个判断是错的**，作废。

真实原因：`City(name, latitude, longitude, timezone)` 字段顺序是纬度在前，但我把 8 个城市全按「经度, 纬度」填了。中国城市经度 100–125 全部超出纬度 ±90，上游直接回 400：

```
{"reason":"Latitude must be in range of -90 to 90°. Given: 120.155.","error":true}
```

链路里表现为 `502 天气服务返回 HTTP 400`。我当时先看到 `urllib` 的 `handshake operation timed out` 就下了「网络不通」的结论，没去核对参数——两个现象撞在一起，选了错的那个。

**修法**：8 个城市按 (纬度, 经度) 重填；`City.__post_init__` 加范围校验（纬度 -90~90、经度 -180~180，越界 `raise ValueError` 带城市名），这类错误在 import 时就炸，不用等上游。范围没有放宽。

**规矩（新增）**：假上游只能验流程，**验不出参数对不对**。凡是往后端之外拼请求参数的（坐标、日期格式、字段名、单位），都必须有一条 golden 断言直接断言参数本身，不能只断言「拿到 200」。

对应的 golden 测试（`backend/tests/test_weather.py`）：

- 杭州纬度 ≈30.274（±1）、经度 ≈120.155（±1），且 `latitude < 90 < longitude`
- 每个城市都满足 `-90 <= lat <= 90`
- `weather._params(杭州)` 里 `latitude == city.latitude`（不是经度）
- 故意写反的 `City("写反了", 120.155, 30.274, ...)` 必须抛 `ValueError`

### 验收状态（真上游，已执行）

修正后打真实 Open-Meteo：

| 请求 | 结果 |
|---|---|
| `GET /api/weather?city=杭州`（首次） | **200**，914ms，`cached=false` |
| 10 秒内第二次 | **200**，1ms，`cached=true` |
| `city=瞎编城市` | **400**，detail 列出可选城市 |
| `city=上海` | **200** |

杭州 2026-11-21 的真实返回（给用户跟手机天气核对）：

```json
{"city":"杭州","date":"2026-11-21","t_min":3.1,"t_max":15.5,
 "feels_min":0.8,"feels_max":13.2,"precip_prob":0.0,"wind":6.5,"uv":4.45,
 "cached":false,"stale":false}
```

单位经实测确认：温度 ℃、风速 km/h、降水 %、UV 无量纲。

| 测试 | 结果 |
|---|---|
| `pytest backend/tests` | **28 passed**（原 16 + 天气 8 + golden 4） |

## 22. N2：规则候选生成（2026-11-21）

### 分层

- `app/rules.py` 是纯函数：不 import Session/httpx、不查库，输入 `WeatherFacts` + `list[RuleItem]` + occasion，输出 `RecommendPlan`。路由 `app/routers/recommend.py` 只做「查库 → 映射 → 调规则 → 拼响应」。
- 这样测试可以对同一个规则层喂人造衣橱，不需要数据库，也不会被网络波动影响。

### 字段推导（因为库里这两列 100% 为空）

- `layer_of`：outer→outer；top/dress→inner；bottom/shoes/accessory→None（不参与层）。
- `formality_of`：work→4、formal→5、sport→1、casual→2；未知按 casual。
- `season` 完全不参与：全空，且日预报已经覆盖温度信息。

### 阈值（常量集中，测试里也断言了常量值）

```
COLD_FEELS_MIN=7   MILD_FEELS_MIN=17   OUTER_FEELS_MIN=12
DIFF_SPREAD=9      DIFF_FEELS_MIN=18
```

用**体感**而不是实测温度：`feels_min < 7` → warmth 3；`< 17` → 2；否则 1。外套看 `feels_min < 12`；打底看「温差 ≥9 且早间 <18」。

**为什么把 5/15 提到 7/17（迟滞）**：天气源在不同模型之间差 ±2–3℃（同一天 best_match 3.1、CMA 6.8），硬边界会让同一天在小幅波动里反复翻档。穿搭场景下宁可穿厚，所以把「冷」和「凉」的门槛各抬高 2℃。测试里用 `6.5→3`、`16.0→2` 两条钉住改动生效。

### 组套与打分

- 基础 top 1 + bottom 1 + shoes 1；有连衣裙时生成「连衣裙 + 鞋」的替代方案。
- `need_outer` 加一件外套；`need_extra` 再补一件比目标薄一档的上衣（理由里叫「打底」）。
- 打分：`|warmth − need|` 为主键、场合正式度差为次键、id 兜底，保证确定性；候选去重后取前 3。
- **三套要有实质差异**：按排序取候选时记录 `(下装 id, 鞋 id)` 组合（裙装方案记 `(连衣裙 id, 鞋 id)`），同一组合只用一次；凑不满 3 套才允许重复组合。这样三套不会再「只换上衣」。
- 同一套里 id 不许重复；三套之间至少一件不同（用 frozenset(ids) 去重保证）。
- `warmth` 为空的单品按「中」参与打分，不直接排除——否则半柜子数据用不上。

### 边界

- 空衣橱 / 缺鞋 / 缺上衣且无裙 → 0 套 + `notice`，**不抛 500**。
- 缺下装但有连衣裙 → 出裙装套数，不算缺件。
- 缺外套但天冷 → 照常出套，`notice` 提一句缺外套。
- 天气 502 由 `resolve_weather` 原样往上抛，推荐接口不吞。

### 验收（已执行）

| 项 | 结果 |
|---|---|
| 规则单测（人造衣橱） | 30 条：阈值（含迟滞 6.5→3 / 16.0→2）、layer/formality、-5℃ 全含外套、30℃ 无外套且无 warmth=3、缺下装/缺鞋/空衣橱、occasion 过滤、三套互异、**三套基础组合互不相同**、**只有 1 条下装仍出 3 套**、确定性 |
| 接口契约测试 | 2 条：返回结构、天气 502 透传 |
| 全量 pytest | **74 passed**（70 + 迟滞 2 + 多样性 2） |
| 真实衣橱 + 真实天气 | 54 件，`occasion=casual` 返回 3 套，基础组合 `(17,19) / (17,34) / (57,19)` 三组互不相同，`notice=null` |

真实返回样例（2026-11-21，体感 0.8–13.2℃）：

```
体感 0.8–13.2℃，中上衣 + 中打底 + 厚外套 + 厚下装 + 厚鞋 + 薄配饰；早晚温差大，加了一层打底
```

### 已知局限（有意留给后续）

- ~~三套之间只换上衣~~ **已修（N2b）**：基础组合去重后，真实衣橱下三套的下装/鞋分别是 `(17,19) / (17,34) / (57,19)`。衣橱里下装和鞋都只有 1 件时才会退化成重复组合。
- `occasion=work` 时会出现「连衣裙 + 打底上衣 + 外套」，语义上略怪，规则没有「裙装不叠打底」的约束。
- 完全没用降水/紫外线（只按体感配），雨天该不该换鞋还没规则。
- 没落库、没接模型（N3）、`wear_log` 不参与打分（按范围）。

## 23. N3：搭配页 + 保存搭配（2026-11-21）

### 后端契约

- `POST /api/outfits`：`{item_ids, weather?, note?}`。校验 item_ids 非空、每个都存在于未删除的单品，否则 422；单件重复会被折叠（不是报错），因为 `outfit_items` 有 `UNIQUE(outfit_id, item_id)`。
- `worn_on` = `weather.date`，没传天气就用服务器当天；`weather_json` 存整份快照（含 `weather_text`），以后能解释「当时为什么这么配」。
- `layer` 用 `rules.layer_of(category)` 填：top/dress→inner、outer→outer、其余 null。
- **同一套重复提交不去重**：那是「今天又穿了这套」，是合法记录。
- `GET /api/outfits?limit=20`：带 `item_ids`，够当前验证用，历史页留给以后。
- `DELETE /api/outfits/{id}`（N3b）：软删只打 `deleted_at`，`outfit_items` 不动——`wear_log` 视图本来就按 `outfits.deleted_at IS NULL` 过滤，所以删完视图里自然没有这几行。id 不存在或已删都返回 404。
- 不做编辑 / 撤销（按范围）。

### 前端

- 第三个 tab「搭配」：天气条（城市/文案/温度/体感/降水/UV）+ 四场合切换 + 三张卡片（缩略图横排 + 理由 + 「就穿这套」）。
- 点按钮 → `POST /api/outfits` → toast「已记下今天的搭配」→ 按钮变「已保存」并禁用，防连点。
- 加载失败（400/502）显示错误文案 + 重试按钮，不白屏。
- 所有请求走 `core/api.ts`（`getRecommend` / `saveOutfit`），组件里没有裸 `fetch`。

### 验收（已执行，走真实接口 + 真实库）

| 项 | 结果 |
|---|---|
| a) 推荐数据 | `occasion=casual` → 3 套，天气「晴 6.8–14.6℃」，每套 5 件且 5/5 有缩略图 |
| b) 保存落库 | `outfits 0→1`、`outfit_items 0→5`；layer 为 inner/None/None/outer/None；`wear_log` 查到 5 行（item_id 1/5/16/17/19） |
| c) 切 work | casual ids `[1,5,16,17,19,34,57]` vs work ids `[13,18,28,32,33,34]`，内容确实换了一批 |
| 后端测试 | 81 passed（74 + 搭配 7） |
| 前端 | 23 passed / typecheck 0 / build 0（271KB，gzip 84KB） |

**未执行**：浏览器里真点「就穿这套」。沙箱起不了浏览器，所以按「前端会发的请求」原样发了一遍 HTTP 并查了库——按钮禁用与 toast 属于纯 UI 行为，仍需你点一次确认。验收期间真的落了一条记录：`outfits.id=1`、`worn_on=2026-11-21`、5 件单品、note「规则推荐 · casual」。不想留可以直接 SQL 删，或者告诉我处理。

### N3b 收尾

- 加了 `DELETE /api/outfits/{id}`，3 条测试（软删、重复删 404、不存在 404），总数 84 passed。
- 用接口（不是改库）删掉了测试搭配：库里当时有 4 条（id 1–4，比你提的 3 条多一条），全部 `DELETE` 返回 204；删后 `GET /api/outfits` → `total=0`、`wear_log` → 0 行、`outfit_items` 17 行原样保留（软删语义）。
- 搭配页天气条右下角加了一行 `数据来源 Open-Meteo`（`text-[10px] text-black/25`），Open-Meteo 的署名要求现在页面上也满足了，不只在 README。
- README 顶部改成「W1 完成 · W2 完成 · W3 进行中」，已补的缺口（Alembic、孤儿图、图库删除 UI）划掉并注明补法。

## 24. N4：LLM 适配层 + 候选集校验（2026-11-21）

### 客户端（`app/llm.py`）

- 默认 `deepseek-chat` + `https://api.deepseek.com`（**不带 `/v1`**，实测这个路径 200），请求路径 `/chat/completions`；`EW_LLM_MODEL` / `EW_LLM_BASE_URL` 可覆盖。本账户可用 `deepseek-chat` 与 `deepseek-v4-pro`。
- **为什么用 chat 不用 flash**：flash 是推理模型，每次多烧 100–170 个 reasoning token、1.2–1.5s；chat 实测 735ms、6 completion tokens，同样支持 `response_format=json_object`。选衣这种小任务用 chat 更省更快。
- `max_tokens` 默认 800（`EW_LLM_MAX_TOKENS` 可配）。**这两个模型带 reasoning tokens**：实测 `max_tokens=30` 时返回 `content=""` 且 `finish_reason="length"`，预算全花在推理上。所以解析前先判：`finish_reason == "length"` 或 `content` 为空 → `LLMError("truncated")`，走修复/降级，**不去 `json.loads("")`**。
- `response_format: json_object` 实测支持；仍保留 ```json 围栏剥离作为容错。响应里的 `reasoning_content` 一律忽略，只解析 `content`。
- OpenAI 兼容的 `POST {base_url}/chat/completions`，`temperature=0`；上游 400 且抱怨 `response_format` 时去掉它重试一次。
- 所有失败折成 `LLMError.reason`：`timeout` / `network` / `rate_limited` / `upstream_5xx` / `http_4xx` / `bad_json` / `bad_structure` / `truncated`。
- key 不做全局单例：`resolve_llm_config(header_key)` 先看 `X-LLM-Key`，再看 `EW_LLM_KEY`，都没有返回 `None`（走规则，不算错误）。
- 预期延迟：flash 约 1.2–1.5s/次、约 200 tokens/次。日志里已有 `elapsed_ms`，N6 前端按这个做 loading 态。

### 候选池与校验（`app/llm_pick.py`）

- 池子复用规则同一套排序（`rules.rank_items`），每类截前几件：top 4 / bottom 3 / shoes 3 / outer 3（仅需外套时）/ accessory 2，总数 10–15。
- **校验才是重点**，不是 prompt：prompt 里写「只能从给定 id 中选」只是提示，真正拦住幻觉的是四条硬校验——整数数组、长度 3–6、id 全在池内、不重复、品类齐全（top 或 dress / bottom 或 dress / shoes，需外套时还要 outer）。
- 校验失败把「哪些 id 非法、缺了哪类」原样回灌，让模型重出一次；第二次仍失败降级规则，`fallback_reason=invalid_ids|invalid_outfit`，不抛异常。
- **池子里没有的品类不要求模型选**：衣橱没外套时 `want_outer` 自动降级为 false；连 top/bottom/shoes 都凑不齐就直接 `missing_category` 降级，不浪费一次调用。（这个坑是测试跑出来的：规则结果没有外套，校验却要求外套，导致永远降级并多打一次模型。）

### 接口（`app/routers/recommend.py`）

- `mode=rules`（默认）不变；`mode=llm` 时只**替换第一套**，后两套仍是规则结果，响应带 `source` / `attempts` / `fallback_reason`。
- 没 key → `fallback_reason=no_key`，完全不调用上游；模型失败 → 整套退回规则 3 套。**模型问题永远 200**；天气 502 仍照常往上抛（那是另一回事）。
- 日志只有 `mode / source / attempts / fallback / elapsed_ms / key 指纹`，不记明文 key、不记 prompt、不记响应体。指纹是 sha256 前 8 位。

### 测试

`backend/tests/test_llm.py` 30 条，全部 mock httpx：

| 覆盖 | 断言 |
|---|---|
| 正常 | `source=llm`、`attempts=1`、outfit/reason 正确 |
| 幻觉一次 | 第二次合法 → `source=llm`、`attempts=2`，且第二次 prompt 里带了「候选池」错误 |
| 幻觉两次 | `source=rules`、`fallback_reason=invalid_ids`、仍有规则结果 |
| 重复 id / 长度 2 / 长度 8 / 缺下装 / 缺外套 / 非整数 | 各自判失败并给出对应问题 |
| 429 / 超时 / 非 JSON / 结构不对 | 降级且 reason 正确 |
| **截断**（`content=""` + `finish_reason=length`） | `LLMError("truncated")`；接口层降级为规则，200，`fallback_reason=truncated` |
| 空正文但没标 length | 同样按 `truncated` 处理 |
| payload | `model=deepseek-chat`、`max_tokens=800`、`temperature=0`、`response_format=json_object` |
| `reasoning_content` | 有它也不影响，只解析 `content` |
| 默认配置 | 不带 `/v1` 的 base_url、flash 模型、800 预算；`EW_LLM_MODEL` / `EW_LLM_MAX_TOKENS` 可改 |
| 无 key | 走规则，`chat_calls == 0` |
| 日志 | caplog 里没有明文 key，有指纹 |

`pytest.ini` 新增（`asyncio_mode=auto`），`requirements-dev.txt` 加 `pytest-asyncio`——测试里要用 async，不想让每个用例手写事件循环。

全量：**121 passed**（84 + 37）。

**顺带修的一个统计 bug**：`attempts` 原来在 LLMError 分支返回 `attempt - 1`，第一次就失败时显示 0 次——明明已经调过一次。改成返回实际调用次数。

### 候选池漏 dressing：LLM 路径比规则更严格（N4 修正）

**现象**：`mode=llm&occasion=formal` 直接 `source=rules`、`attempts=0`、`fallback_reason=missing_category`，模型一次都没被调用。而规则层能给 formal 出裙装方案。

**原因**：`POOL_SIZES` 里只有 top/bottom/shoes/outer/accessory，**没有 dress**。formal 衣橱按场合筛完是 top 18 / outer 6 / shoes 2 / dress 2 / bottom 0，池子里既没下装也没连衣裙，而校验要求「bottom 或 dress」→ 永远不满足 → 提前降级。

**修法**：

1. `POOL_SIZES` 加 `"dress": 2`。
2. `missing_category` 的判定只按池子里**实际有的**品类算：需要 (top 或 dress) 且 (bottom 或 dress) 且 shoes；天冷时还要池里有 outer。缺任何一项才跳过模型。
3. 补两条测试：只有 dress+shoes 的衣橱必须调用模型；formal 形态（bottom=0、dress=2）不再 `missing_category`。

**验证**（真实衣橱 + 假上游，四个场合一遍）：

```
formal  ids=[2, 21, 10, 14]       -> source=llm attempts=1 fallback=None
casual  ids=[1, 17, 19, 16, 5]    -> source=llm attempts=1 fallback=None
work    ids=[13, 18, 32]          -> source=llm attempts=1 fallback=None
sport   ids=[9, 34, 3]            -> source=llm attempts=1 fallback=None
```

全量 **124 passed**（121 + 3）。

**教训**：候选池的品类清单和校验的必备品类必须成对维护——池子少一类，校验就会要求一个模型永远选不出来的东西，而且表现为「静默降级」，不看日志根本发现不了。

## 25. N5：推荐结果缓存 + 限流（2026-11-21）

### 缓存（`app/llm_cache.py`）

- key = `(date, occasion or "", weather_hash, wardrobe_hash, mode)`：
  - `weather_hash`：`t_min / t_max / feels_min / feels_max / precip_prob / weather_code` 拼起来 sha256 前 12 位；
  - `wardrobe_hash`：未删单品的 `id:updated_at` 拼起来 sha256 前 12 位——改任何一件衣服都会失效，这是有意的。
- **只缓存 `source="llm"` 的成功结果**。降级结果（rules / timeout / invalid_ids / rate_limited）绝不入缓存，否则一次抽风会被钉住半小时。日志里有 `llm_cache skip=fallback reason=…` 便于确认。
- TTL 30 分钟（`EW_LLM_CACHE_TTL`），进程内 dict，上限 200 条，超了按写入时间淘汰最旧。命中返回 `cached=true`。
- 天气服务自己还有一层 2 小时快照缓存；两层互不影响，但测试「换天气」时记得清天气缓存，否则取的还是旧快照。

### 限流（`app/limits.py`）

- 只对「mode=llm 且真的要调模型」计数：命中缓存不计、mode=rules 不计。
- 滑动窗口 60 秒，按客户端 IP（`X-Forwarded-For` 优先，取第一个值；否则 `request.client.host`），默认 10 次/分钟（`EW_LLM_RATE_LIMIT_PER_MIN`）。
- **超限不返回 429**：200 + `source=rules` + `fallback_reason=rate_limited` + `notice`「请求太频繁，当前展示的是规则推荐」，响应头带 `X-RateLimit-Remaining`（超限时为 0）。原则是这个应用不该因为自己的限制把页面搞挂。
- 每次调用会 prune 当前 key 的过期窗口；bucket 总数超过 500 时顺手清理空窗口，避免 dict 无限增长。

### 局限（写清楚，别假装没有）

- 缓存与计数都是**进程内**的：单进程 uvicorn 够用；一旦开多 worker 或上多实例，每个进程各一份，命中率和限流都是「每进程」口径。要共享得换 Redis，N5 不做。
- 限流按 IP，同一台机器上的多个浏览器/标签页共享额度；NAT 后面的人会互相影响。
- `X-Forwarded-For` 可伪造，只有放在可信反代后面才有意义。

### 测试

`backend/tests/test_llm.py` 新增 9 条（全 132 passed，跑了两遍确认不依赖顺序/DB 残留）：

| 场景 | 断言 |
|---|---|
| 同请求两次 | 第二次 `cached=true`，上游只调 1 次 |
| 改一件单品 | `updated_at` 变 → 缓存失效，上游再调 1 次 |
| 换 occasion / 换天气 | key 不同；换回原场合仍命中旧缓存 |
| 降级不缓存 | 第一次 429 降级，第二次仍会调上游并成功 |
| 限流 | 上限 2，第 3 次 → 200 + rules + rate_limited + `X-RateLimit-Remaining: 0`，上游调用停在 2 |
| 命中不占额度 | 上限 2 时，命中一次后仍能再调一次真实模型 |
| mode=rules | 不碰缓存、不碰限流 |

### 踩到的测试坑

`_ensure_wardrobe` 原来只按「品类是否存在」补数据，但业务上按场合过滤：衣橱里 top 全是 `work` 时，`occasion=casual` 依然组不出搭配。改成保证每类都有**一件 occasion 为空**的单品（任何场合都可用），顺便避免补数据导致 `wardrobe_hash` 中途变化、把缓存测试搞成玄学。

## 26. N5b：天气请求超时重试（2026-11-21）

### 背景

`api.open-meteo.com` 在本机**间歇性 TLS 握手超时**：TCP 283ms 能连，TLS 有时 20 秒超时、有时 591ms 成功。原来单次失败就 502，重启撞上这个窗口整页不可用。

### 改法（只动 `weather.py`）

- `fetch_daily` 里对 **`httpx.TimeoutException`**（含 ConnectTimeout / ReadTimeout / 池超时）重试 1 次，间隔 `RETRY_DELAY_SECONDS=0.5`。
- **HTTP 4xx/5xx 不重试**：重试也不会变好，还多花一次请求。
- **其他连接类错误（DNS 失败、连接被拒）也不重试**：换时间不会好，属于配置/网络问题，让它快速失败。
- 重试日志：`weather retry city=杭州 attempt=2`；两次都失败才抛 `UpstreamError`，接口照旧 502。
- 测试里把 `RETRY_DELAY_SECONDS` patch 成 0，避免真睡。

### 验证

- 单测 4 条：第一次超时第二次成功（200、`cached=false`、上游调用 2 次、日志含 retry）；两次超时 → 502 且 2 次调用；HTTP 400 → 502 且**只调 1 次**；HTTP 500 → 同上。
- 手动：把 `API_URL` 指到不可路由地址 `https://10.255.255.1`，日志出现一次 `weather retry city=杭州 attempt=2`，耗时 2.3s 后 `UpstreamError`——确认「两次尝试」真的发生。
- 真实上游当前可达时：一次成功（976ms，杭州 6.8–14.6，未触发重试）。

全量 **136 passed**。

### 局限

- 只重试超时，且只重试一次；TLS 若持续抽风仍会 502。
- **没有持久化「上次成功的天气」**：进程重启后无缓存可用，冷启动撞上不可用窗口就是 502。这条留给 W4 部署阶段（需要新表或落盘文件），本轮按范围不做。

## 27. N6：模型调用指标落库（2026-11-21）

### 表

`llm_metrics`（迁移 `4daad94c5afe`）：`id / created_at / mode / source / cached / attempts / fallback_reason / latency_ms / model / tokens_prompt / tokens_completion / is_byok`。`created_at` 建了索引，`/api/metrics` 按它过滤。

只记 `mode=llm` 的请求——`mode=rules` 是纯本地计算，记进来只会稀释成功率。

### usage 透传

`chat_json` 的返回值从 `dict` 改成 `(data, usage)`，`usage = {prompt_tokens, completion_tokens}`。**取不到就是 `None`，不填 0**——0 是「真的花了 0 个 token」，None 是「上游没告诉我们」，两者在成本统计里含义完全不同。`llm_pick` 把它塞进 `PickResult.usage`，路由层负责落库。

### 记录点

- 路由结束时写一行，**成功 / 降级 / 限流 / 无 key 都写**，`cached=true` 也写（这样能算缓存命中率）。
- 命中缓存那行的 `attempts=0`：这次请求确实没调模型（接口返回的 `attempts` 仍是缓存里记录的调用次数，两个语义分开）。
- 整段写入包在 `try/except` 里，失败只 `logger.warning(..., exc_info=True)` + `rollback()`，**不影响响应**。
- 日志仍是原来那六个字段，**不加 token**：日志用来排障，指标用来算账，两条路。

### 聚合

`GET /api/metrics?days=7`（1–90）：

- `total_calls` / `llm_success`（source=llm 且未命中缓存）/ `cache_hits` / `fallbacks` / `fallback_by_reason` / `by_model` / `tokens` / `byok_calls` / `server_key_calls`。
- `latency_ms` 的 **p50/p95 用 SQL `ORDER BY … LIMIT 1 OFFSET n` 取**，不把整表拉进内存；`avg` 走 `AVG()`。offset 用 `int(total×分位)` 并夹在 `total-1` 内，是近似分位（够用，不追求严格插值）。

### 验证

单测 7 条（`backend/tests/test_metrics.py`，全 mock 上游）：

| 场景 | 断言 |
|---|---|
| 成功一次 | 1 行；`source=llm`、`cached=false`、`attempts=1`、tokens=82/15、`is_byok=true` |
| 429 降级 | 1 行；`source=rules`、`fallback_reason=rate_limited`、tokens 为 None |
| 无 key | 1 行；`fallback_reason=no_key`、`attempts=0`、`model=None` |
| 缓存命中 | 两次请求两行，第二行 `cached=true`、`attempts=0`，上游只调 1 次 |
| 写指标失败 | `Session.commit` 抛异常时接口仍 200 |
| 聚合 | 插入 6 条新 + 1 条 30 天前：`total=6`、`llm_success=4`、`cache_hits=1`、`fallbacks=1`、`tokens=320/80`、`byok=5`、`avg=200.0`、`p95>=p50` |
| days 校验 | 0 和 91 都 422 |

全量 **144 passed**。

**真实库验收**（8001，无 key 连打 20 次，用 no_key 路径验证记录与聚合，不消耗额度）：

```
before: total_calls=0
after : total_calls=20, fallbacks=20, fallback_by_reason={"no_key": 20},
        server_key_calls=20, latency_ms={"avg":50.8,"p50":2,"p95":975}
```

数字与手数完全对得上（第一次 975ms 含取天气，之后天气命中缓存都是 2ms，所以 avg 被拉低）。这 20 行留在库里，不需要可以 `DELETE FROM llm_metrics`。

### 局限

- 不清理旧指标：表会一直长，行数多了要加定期删除（本轮按范围不做）。
- 不做 Prometheus 格式，也不做前端图表。
- p50/p95 是 offset 近似分位，不是严格插值。
- 指标落的是**单库单进程**口径；将来多实例部署时这张表会变成共享计数，反而正好可以用。

### 口径修正（N6b）：by_model 曾经虚高

**现象**：实测 `/api/metrics` 里 `by_model=14`，而真实模型调用只有 1 次。

**原因**：`by_model` 的条件是 `model is not None`，但缓存命中、`rate_limited`、`missing_category`、`no_key` 这些请求只要带了 key，也会把 `model` 写进行里（模型名是配置项，不是「调用了」的证据）。于是「配置了模型」被当成了「调用了模型」。

**修法**：

1. `by_model` 加 `attempts > 0`：只统计真的发起了模型调用的请求。现在 `by_model` 的合计 == `llm_success`。
2. 新增 `model_latency_ms`（avg/p50/p95），只统计 `attempts > 0` 的行——**对外报延迟用这个**。原来的 `latency_ms` 保留为「请求级耗时」（含缓存命中、限流这些 2ms 的快速请求，会把平均值拉得很低，不适合当模型延迟）。两个字段的注释都写清了。
3. `tokens` 注明只累加非空值：降级请求记 `None`，不会被当成 0。

**测试**：造 3 行（缓存命中 2ms / 成功 800ms / 降级 3ms）：

- `by_model = {"deepseek-chat": 1}`、`llm_success = 1`；
- `model_latency_ms.avg = 800.0`、`latency_ms.avg = 268.3`；
- 没有任何 `attempts>0` 的行时，`model_latency_ms` 三个值都是 `null`（不是 0）。

**真实调用验证**（本地起一个假 DeepSeek，应用真走一次 HTTP 模型调用，不花额度）：

```
recommend: 200 source=llm attempts=1
llm_success = 2   by_model = {"deepseek-chat": 2}   ← 两个数字一致
model_latency_ms = {"avg": 836.5, "p50": 910, "p95": 910}
latency_ms       = {"avg": 75.5,  "p50": 2,   "p95": 910}
```

对比很直观：请求级平均 75.5ms 被缓存命中拉低，模型级 836.5ms 才是要报的数字。

全量 **146 passed**（144 + 2）。

## 28. N7：前端接模型（BYOK + AI 开关）（2026-11-21）

### key 的存取

- `adapters/llmKey.ts`：`getLlmKey / setLlmKey / clearLlmKey`，读写 `localStorage['ew.llmKey']`。放 adapters 是因为 `core/` 不许碰 `window`。
- key **只走请求头 `X-LLM-Key`**：不进 URL、不进日志、页面只回显 `maskKey()` 打码后的 `sk-****`，输入框 `type="password"`，不提供「显示」按钮。
- **风险（接受）**：localStorage 明文 + 同源 XSS 可读。这是 BYOK 的既有取舍（服务端不落库、不写日志，换来「key 只属于使用者」）；真要更强隔离得上后端代理或 WebCrypto，超出范围。
- 清除 key 会同时关掉 AI 开关，避免「开关开着但没 key」这种半吊子状态。

### 请求与状态

- `core/api.ts` 的 `getRecommend({ mode, llmKey, occasion, city })`：`mode=llm` 且给了 key 才带请求头；`request()` 的 headers 改成合并而不是覆盖，否则自定义头会把 `Content-Type` 顶掉。
- 返回类型补上 `source / attempts / fallback_reason / cached`。
- 徽标与文案在 `core/recommendBadge.ts`（纯函数，12 条单测）：`llm+cached=false → AI 精选`、`llm+cached=true → AI 精选 · 缓存`、`rules → 规则推荐 + 降级原因`。原因映射覆盖 `no_key / rate_limited / timeout / invalid_ids / invalid_outfit / truncated / missing_category / bad_json / network` 等，未知原因兜底「模型暂时不可用」。

### 加载与超时

- 模型正常 0.8–1.2s；后端最坏会等 ~10.5s（天气两次 5s 超时 + 0.5s 间隔）。所以前端设 **12s** 超时：AI 请求超过 12s 没回来就 `setAiMode(false)` 退回规则并 toast「这次有点慢，先给你规则推荐」。
- 请求期间显示 `AI 正在挑衣服…`（`animate-pulse`），并用 `keepPreviousData` 保留上一批卡片，避免整块闪空。
- 超时只是「前端不再等」，后端那次请求仍会跑完并记指标——这是有意的：宁可多一条指标，也不要中止后端写库。

### 设置弹层

- 右上角「⚙ 设置」打开固定定位弹层（点遮罩关闭，点面板不关）：状态文案「已配置（sk-****）/ 未配置」、密码框、保存、清除。
- AI 开关在没 key 时是「视觉禁用」但**仍可点**：点了给 toast「先配置 API key」并自动打开设置弹层——真 `disabled` 的按钮点不了，用户会以为坏了。
- 切换场合保持 AI 开关状态；切到别的 tab 再回来，组件重挂载，开关回到关、弹层关闭（不会重复弹）。

### 验证

| 项 | 结果 |
|---|---|
| 前端单测 | **35 passed**（原 23 + 徽标/文案 12） |
| typecheck / build | 0 / 0（275KB，gzip 85KB） |
| 构建产物含关键文案 | `AI 精选`、`AI 精选 · 缓存`、`规则推荐`、`先配置 API key`、`X-LLM-Key`、`ew.llmKey`、`AI 正在挑衣服` 全部命中 |
| 后端契约（8000 实测） | `GET /api/recommend?mode=llm` 无 key → `source=rules, cached=false, fallback_reason=no_key, attempts=0` |
| 浏览器里的 a–e | **未执行**（沙箱起不了浏览器），需要人工点 |

### 局限

- AI 开关不持久化：刷新后回到「关」，要再点一次。
- 保存 key 前不做校验（不试打一次），填错要等第一次请求才发现——那样会白等一次超时。
- 前端 12s 超时后不会取消后端请求。
- key 明文存 localStorage，见上面的风险说明。

### 弹层两态 + 显隐切换（N7b）

**改法**：

- 弹层分两态。未配置：空输入框 +「保存」+ 提示「在 DeepSeek 后台创建，形如 sk-...」。已配置：状态行「已配置（sk-****）」+ 眼睛按钮（可临时看全）+「更换」「清除」；点「更换」才展开输入框并自动聚焦，保存后回到已配置态。
- 输入框和状态行各有一个眼睛按钮，`aria-label` 分别是「显示 key」/「隐藏 key」，图标用内联 SVG（睁眼/闭眼）随状态切换。
- 输入框里按 `Enter` = 点保存。
- 明文只在弹层里可见：关掉弹层即复位（`revealSaved`/`showDraft` 都置 false）；不进日志、不进 URL，请求之外不落任何地方。
- 清除 → 回未配置态 + 关掉 AI 开关；保存 → toast「已保存」+ 切到已配置态。

**又一次踩到「dev server 喂旧模块」**：改完后源码里明明有「更换」，但 5173 返回的模块里还是旧弹层（状态变量是新的、JSX 是旧的）。这是 DECISIONS 19 那条老问题：vite 的 watcher 早前报过 `EBUSY`，之后不再失效模块图。**验收 N7b 之前必须重启 `.\dev.cmd`**，否则看到的是旧弹层。构建产物（dist）是新的，字符串都在。

### 验证（N7b）

| 项 | 结果 |
|---|---|
| 前端单测 | 35 passed（无新增，纯 UI 改动） |
| typecheck / build | 0 / 0（278KB / gzip 86KB） |
| dist 含关键文案 | 「更换」「取消」「显示 key」「隐藏 key」「已配置」「形如 sk-...」全部命中 |
| 浏览器里 a–d | **未执行**（无浏览器），且需先重启 dev server |

### 图标语义修正 + 根治 stale module（N7c）

- **眼睛图标改成反映当前状态**而不是下一步动作：key 可见 → 睁眼（`EyeIcon`），key 隐藏 → 斜线眼（`EyeOffIcon`）。`aria-label` 与 `title` 仍保持**动作语义**（可见时「隐藏 key」、隐藏时「显示 key」），两处按钮都加了 `title`，悬停能看到提示。之前的实现是反的，用户读成「点它会把眼睛闭上」，实际是「已经是闭眼状态」。
- **`vite.config.ts` 开轮询**：`server.watch = { usePolling: true, interval: 300 }`。今天已经三次「源码改了、5173 还是旧模块」，每次排查半小时；Windows 上 Vite 的 watcher 在 EBUSY 之后不再失效模块图，轮询用少量 CPU 换确定性。
- **实测轮询生效**：另起一个 5199 的 dev server，写一个探针文件 `MARK-ONE` → 改成 `MARK-TWO`，不重启、2 秒后再请求，拿到的是 `MARK-TWO`。探针已删除。
- 注意：轮询只对**新启动**的 dev server 生效；当前 5173 那个旧进程仍是坏的，验收前要重启 `.\dev.cmd`。

### 未执行

想在 8001 上跑一次真实降级链（无 key / 无效 key 各一次），但 Open-Meteo 这时又连不上（`ConnectTimeout`），`/api/recommend` 在天气那一步就 502 了，到不了 LLM。所以：

- 无 key、模型失败、修复、日志不含明文 key **都有 mock 到路由层**的用例兜着；
- **真实上游 + 真实 key 的组合没有跑过**，等 N5 接指标落库时一并补。

### 顺带发现的环境问题

本机 8000 端口上跑的是**修正前**的进程（打 `city=杭州` 还回 `502 天气服务返回 HTTP 400`，和你看到的现象一致）。它由本会话之外的终端启动，当前沙箱会话对它 `Stop-Process`/`taskkill` 都返回「拒绝访问」，杀不掉，所以本轮真上游验证改在 **8001** 端口做。

**你需要做的**：把那个 8000 的进程停掉再 `.\dev.cmd`，否则新代码不会生效——这是上一轮「改了没生效」的同类问题，只不过这次是进程而不是 dev server 缓存。


