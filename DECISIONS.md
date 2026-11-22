# 决策记录

按时间倒序不重要，按「以后会忘、忘了会返工」排序。每条都写清「选了什么 / 为什么 / 什么时候该推翻」。

> **展示名变更（2026-11-22）**：产品展示名已从「电子衣柜」改为「小柜子」（英文仓库名 little-wardrobe 不变）。本文件历史记录中的「电子衣柜」均指同一产品，不再回改。

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

**代价**：如果用户传了图但没保存单品，会留下孤儿图。目前没有清理任务（`scripts/clean_media.py` 只能清不再被引用的文件，孤儿图仍挂在 `images` 表上）。
**什么时候补**：W2 之前加一个「启动时删掉 24 小时前的孤儿图」的小任务就够，别上定时框架。

**修订（W7a，2026-11-22）**：原来写的是「不做图片识别」。改成「**只做录入时的品类/厚薄预填**」——这两个是极速录入里最明显、也最浪费时间的两步，识别它们直接服务主流程。颜色、材质、品牌、精细子分类**仍然不做**，那属于「看起来酷但不影响核心动作」的范畴。

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

**局域网模式（W4e）**：`.\dev.cmd -Lan` 只把**前端**放到 `0.0.0.0`（`vite --host`），uvicorn 仍监听 `127.0.0.1`。理由：手机访问 5173，vite 的 proxy 在 dev server 内部转发 `/api`、`/media`，所以 8000（含 `/docs` 和所有写接口）不需要暴露给同 WiFi 的其他人，暴露面只有只读页面本身。

**坑**：`pnpm dev -- --host` 在 pnpm 11 下**不生效**——pnpm 把 `--` 原样传给脚本，vite 把它当成「参数结束」，`--host` 被忽略（实测仍只绑 127.0.0.1）。必须写 `pnpm dev --host`（不带分隔符）。`dev.ps1` 里已按后者实现并注释。

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

1. `by_model` 加 `attempts > 0`：只统计真的发起了模型调用的请求。**注意 `by_model` ≠ `llm_success`**：一次调用失败（比如 `http_401`）也计入了 `by_model`，但不计入成功数——两个数字在「有失败调用」时本来就会差 1，差值正好等于「尝试了但失败」的次数。
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

## 29. W5a：手机端录入修复（HEIC / 拍照相册分离 / 错误文案）（2026-11-21）

### 两个入口

原来只有一个 `<input capture="environment" multiple>`：带 `capture` 时手机一律进相机，相册选不了；`capture` 与 `multiple` 同时存在的行为在各家浏览器也不一致。拆成两个 input：

- 「📷 拍照」：`accept="image/*" capture="environment"`
- 「🖼 从相册选」：`accept="image/*" multiple`

两个共用同一个 `onPick()`（`addFiles` → 清 `value` → `blur` → 焦点交还容器），桌面浏览器忽略 `capture`，两个按钮都只是文件选择。

### HEIC/HEIF

- 装了 `pillow-heif`，`imaging.py` 在 Pillow 导入之后执行 `register_heif_opener()`；`ALLOWED_SUFFIXES` 增加 `.heic` / `.heif`。
- 管线不变：`exif_transpose` → `convert("RGB")` → 重建图 → 双档 WebP。HEIC 的 10bit/多帧在 `convert("RGB")` 这一步统一，解不开就 `UnsupportedImage` → 415。
- 415 的文案从「图片无法解析，可能已损坏」改成「图片无法解析，格式可能不受支持」——带上「格式」两个字，前端才能可靠地映射成 iPhone 提示（否则 `broken.heic` 这种场景匹配不上）。

### 前端错误文案

`core/uploadError.ts` 的 `uploadErrorMessage(status, detail)`：415 且 detail 含「格式」→ iPhone 设置提示；413 → 压缩到 12MB 提示；其他原样返回。`adapters/upload.ts` 调用它，组件不重复写映射。

### 事故记录：`pip --upgrade` 把 Pillow 的 `.py` 删了

装 `pillow-heif` 时用了 `pip install --upgrade --target backend\.pyenv`。`--upgrade` 会先删旧包再装新包，而 Pillow 的 `_imaging.cp312-win_amd64.pyd` 正被运行中的 API 进程锁着，删除失败 → **PIL 目录被删了一半**（只剩 `.pyd` 和 `.pyi`，`Image.py` 等 106 个文件没了），`from PIL import Image` 直接 ImportError。

修法：用临时目录装一份同版本 `pillow==13.0.0`，只把缺失的 `.py` 回填进 `backend\.pyenv\PIL`，保留被锁的 `.pyd`（版本相同，二进制一致）。

**教训**：在 `--target` 目录上永远不要用 `--upgrade`；装新包用 `--no-deps`，只补自己那一个。

### 验收（已执行）

| 项 | 结果 |
|---|---|
| 真实 HEIC 上传（带 EXIF orientation=6） | 201，输出 1000×1400（方向已校正），展示图/缩略图均 200 |
| 坏 `.heic`（内容是文本） | 415，detail「图片无法解析，格式可能不受支持」，tmp 不留残file |
| 原有 jpg/png 用例 | 不回退 |
| 后端测试 | **149 passed**（146 + 3） |
| 前端测试 | **41 passed**（38 + 3） |
| typecheck / build | 0 / 0（280KB / gzip 87KB） |
| 手机实机（a–d 里的 b、c） | **未执行**，需要你用手机在 Lan 模式下点一次 |

## 30. W5b：选图后队列为空（2026-11-21）

### 根因

`onPick` 里先 `addFiles(event.target.files)` 传了 **FileList 活引用**，紧接着 `event.target.value = ''` 把 input 清空；而 `addFiles` 内部的 `Array.from(files)` 是在 `setDrafts` 的 updater 里才执行的——那时文件已经没了。桌面 Chrome 偶尔保留旧引用所以侥幸能过，iOS Safari 直接拿到空数组，表现为「确认选图后什么都没发生」。

### 修法

1. `onPick` 第一件事就是快照：`const picked = Array.from(input.files ?? [])`；之后才清 `value`、`blur`、把焦点交还容器。
2. `addFiles` 签名从 `FileList | null` 改成 `File[]`，内部不再 `Array.from`。
3. 纯逻辑抽到 `core/drafts.ts` 的 `appendDrafts(prev, files, make)`：空数组直接返回原数组（no-op），有文件则按顺序追加。这样这条边界能单测（React 组件在本机渲染不了，见第 17 节）。

### 和原始指令的一处不同

指令要求「先 `value = ''`，再兜底延迟读一次 `input.files`」。但 `value = ''` 会立刻清掉 FileList，兜底就永远读不到东西。所以实现成：**快照为空时先不清 value**，`blur` 后 150ms 再读一次；有结果才清并 `addFiles`，仍为空则清掉并 toast「没有取到图片，请再试一次」。成功路径的顺序与指令一致。

### 验证

| 项 | 结果 |
|---|---|
| 前端测试 | **44 passed**（41 + 3） |
| typecheck / build | 0 / 0（280KB / gzip 87KB） |
| dev server 返回的模块 | 已确认 `Array.from` 出现在 `.value = ""` 之前，且含 150ms 兜底与 toast 文案 |
| 手机实机（拍照 → 回页面 → 队列出现 1 张） | **未执行**，需要你验 |

### 二改：入口改成 `<label>` 原生激活（安卓 / 鸿蒙）

**现象**：华为等安卓/鸿蒙浏览器上，点「拍照」「从相册选」确认后队列仍为空；桌面正常。

**原因（推断）**：入口是 `<button onClick={() => inputRef.current?.click()}>`。程序化 `input.click()` 在部分 WebView / 厂商浏览器里会被判成「非用户手势」而静默失败——不弹选择器、不报错，表现就是点了没反应。

**改法**：两个入口改成 `<label role="button" aria-label="…">` **包住真正的 input**，靠 label 的原生激活行为触发文件选择，完全不依赖 JS。input 用 `sr-only` 而不是 `display:none`，这样键盘 Tab 仍能聚焦到它。

`onPick` 同时按「快照 → 清空 → blur → 焦点交还 → addFiles」重排（只有真拿到文件才清空，否则 155ms 兜底重读永远读不到东西）。150ms 兜底与空结果 toast 保留。

**验证**：前端 44 passed / typecheck 0 / build 0；产物里有两个 label、两个 `sr-only` input，且不含任何 `ref.current.click()`。真机仍需用户验。

## 31. W5c：手机端白屏（`crypto.randomUUID` 在非安全上下文不存在）（2026-11-21）

### 根因

`newDraft()` 用 `crypto.randomUUID()` 生成草稿 id。这个 API **只在安全上下文**（https / localhost）存在；手机通过 `http://<局域网IP>:5173` 访问时它是 `undefined`，调用直接抛 `TypeError`。组件没有 ErrorBoundary，异常冒到根节点 → **整页白屏，连报错都看不到**。桌面用 `localhost` 所以一直正常，这类问题只在真机上暴露。

### 修法

1. `core/drafts.ts` 加 `makeDraftId()`：优先 `crypto.randomUUID()`，否则退回 `d-<36进制时间戳>-<随机段>`。
   **`crypto` 在函数里取，不在模块顶层读**——顶层读会让 SSR / 测试环境的差异变成加载期崩溃。
2. 新增 `ui/components/ErrorBoundary.tsx`（class component，官方写法），在 `main.tsx` 里包住整个应用：显示「页面出错了」+ 错误信息（截断 200 字）+「重新加载」按钮。

**为什么值得加 ErrorBoundary**：白屏会让用户以为是网络问题，然后去重启路由器、换手机、卸载重装——真正的错误信息一次都没露过面。把错误摊在页面上，至少能截图发给开发者。成本是一个 class component，收益是以后任何渲染期异常都有出路。

### 局限

- ErrorBoundary 只抓**渲染期**异常；事件回调、`setTimeout`、Promise 里的异常它抓不到（那些不会冒泡到 React 渲染）。
- 它不会自动恢复：点「重新加载」是刷新整页，未保存的草稿会丢。
- 没有上报通道，错误只在用户屏幕上和控制台里。

### 验证

| 项 | 结果 |
|---|---|
| 单测：`makeDraftId` 正常路径 | 36 字符、UUID 形态 |
| 单测：`crypto` 存在但无 `randomUUID` | 仍返回，100 次不重复 |
| 单测：`crypto` 完全不存在 | 不崩，返回非空 |
| 前端测试 | **47 passed**（44 + 3） |
| typecheck / build | 0 / 0（281KB / gzip 87KB） |
| 产物 | 含「页面出错了」「重新加载」；`CapturePage` 里已无裸 `crypto.randomUUID` |
| 手机实机 | **未执行**，需要你验 |

## 32. W5d：天气快照落盘，重启也能降级（2026-11-21）

### 为什么必须落盘

Open-Meteo 在本机一天内实测三次 TLS 握手超时。之前 `stale=true` 只活在进程内存里：上游一挂，`/api/recommend` 就 502 整页不可用；进程一重启，连内存里的旧数据也没了。

### 表与写入

- `weather_snapshots`（迁移 `eac269a89576`）：`city_name` 主键 / `observed_at`（数据对应日期）/ `fetched_at`（抓取时刻 ISO）/ `payload`（`WeatherSnapshot` 的 JSON）。
- 每次**成功**取数后 upsert 一行（同城覆盖），写库包在 try/except 里，失败只 warning——缓存落盘是旁路，不能影响响应。

### 三级降级

| 级别 | 条件 | 结果 |
|---|---|---|
| 1 | 进程内缓存新鲜（<2h） | `cached=true, stale=false` |
| 2 | 进程内缓存过期 | `cached=true, stale=true` |
| 3 | **DB 里的上次快照** | `cached=true, stale=true`，`observed_at`/`fetched_at` 用快照里的 |
| — | 三级都空 | 502 |

`WeatherResult` 与 `WeatherOut` 都加了 `observed_at` / `fetched_at`；前端在 `stale=true` 时显示「⚠ 天气取自 X 小时前的缓存」，不足 1 小时显示「不到 1 小时前」，时间算不出来时退化显示「较早的缓存」。

### 可测性

`API_URL` 常量改成 `api_url()` 函数，读 `EW_WEATHER_URL`（默认 `https://api.open-meteo.com`）。这样能把上游指到不可达地址，真实触发降级，不用等它抽风。

### 验证（真实 HTTP，非 mock）

```
a) normal:            200  stale=False  | weather_snapshots 0 -> 1
b) upstream down:     200  stale=True   observed_at=2026-11-21 fetched_at=2026-11-21T15:34:13+00:00
   recommend:         200  outfits=3
c) clear memory:      200  stale=True      ← 模拟重启，靠 DB
d) delete row + down: 502
```

单测 7 条（`test_weather_persist.py`）：成功写行、同城覆盖不新增、上游挂读 DB、无快照 502、推荐接口也能用快照、写库失败不影响返回、`EW_WEATHER_URL` 生效。

后端 **156 passed**（149 + 7），前端 **50 passed**（47 + 3）。

### 顺带的测试修正

落盘让「上游挂 + 无缓存 → 502」这类旧用例被上一条测试写下的快照兜住了。`test_weather.py` 与 `test_llm.py` 的 autouse fixture 现在每个用例前清空 `weather_snapshots`。

### 局限

- 只有「最后一次成功」，没有历史；同城只存一行。
- 没有过期上限：三个月前的快照也会被当成 stale 返回（前端会显示「N 小时前」，足够暴露问题）。
- 不做多城市清理、不做告警（按范围）。

## 33. W5e：保存反馈闭环 / 媒体清理 / 城市单一来源（2026-11-22）

### ① 保存搭配后的反馈

- `OutfitOut` 增加 `items: [{id, category, thumb_url}]`（最多 6 件，按 `outfit_items.id` 排序）。
- 实现是**两次查询**：先查 outfits（`selectinload(items)`），再把所有涉及的 item_id 用一条 `select(Item).where(Item.id.in_(...))` 取出来——20 条搭配也不会 N+1。
- 缩略图逻辑抽到 `schemas.primary_thumb()`，推荐接口和搭配历史共用；软删的单品保留 `id` 与 `category`，但 `thumb_url` 为 `null`（历史不该因为删了衣服就消失）。
- 前端搭配页底部加「最近穿过」：日期 + 24px 缩略图 + 「N 件」，空状态「还没有保存过搭配」；保存成功后 `invalidateQueries(['outfits'])`，新记录立刻出现。

### ② `scripts/clean_media.py`

- 默认 dry-run，`--apply` 才删；**数据库只读打开**（`file:...?mode=ro`），脚本不写库。
- 可见集合 = 未软删单品的 `images.path` / `thumb_path`；`<stem>_1024.webp` / `_256.webp` 按 stem 归并；originals 用去扩展名的 stem。stem 不在集合里即孤儿。tmp 里的文件一并清。
- 实测：可见 37 件 → originals 63 里 26 个孤儿、derived 126 里 52 个孤儿，共 78 个文件 **118.2 MB**；`--apply` 后 originals 37 / derived 74 / tmp 0，37 件单品的缩略图全部 200（无破图）。

### ③ 城市列表单一来源

- 新增 `GET /api/cities` → `{cities, default}`，直接读 `backend/app/data/cities.py`。
- 前端 `useQuery(['cities'])`（`staleTime` 1 小时）；拿不到就用 `core/cities.ts` 里的 `FALLBACK_CITIES` 兜底，下拉不会因为接口挂了就不可用。
- `resolveCity(raw, available)` 增加第二个参数；后端删了某城市而 localStorage 还存着它时，会自动回落到默认城市。
- 测试里用 `monkeypatch.setitem(CITIES, "测试城", ...)` 验证「后端加一个城市，接口立刻能看到」，用例结束自动还原。

### 验证

| 项 | 结果 |
|---|---|
| 后端 | **161 passed**（159 + 2） |
| 前端 | **50 passed** / typecheck 0 / build 0 |
| 真实接口 | `GET /api/outfits` 带 4 条 brief（category + `/media/derived/..._256.webp`）；`GET /api/cities` 返回 8 城 + 默认杭州 |
| 清理脚本 | dry-run 78 个 / 118.2 MB，apply 后文件数与可见单品一致，缩略图 0 破图 |

验收时创建的那条搭配已用 `DELETE` 软删，`/api/outfits` 回到 0 条（空状态可见）。

## 34. W5f：单品详情 + 补录编辑（2026-11-22）

### 先修的数据不一致

`rules.py` 之前完全按 `category` / `occasion` 推导 `layer` 和正式度，**库里存的值被忽略**——用户补录了也不影响推荐，等于「填了没用」。

改成存量优先：

- `RuleItem` 增加 `formality` / `layer` 两个字段，路由映射时带上 `row.formality` / `row.layer`。
- `layer_of(item)`：`item.layer` 有值就用，否则 `layer_from_category(item.category)`。
- `formality_level(item)`：`item.formality` 有值就用，否则 `formality_of(item.occasion)`；`formality_of(occasion)` 保留，用于「目标正式度」。
- 排序键 `_item_key` 改用 `formality_level`；`llm_pick` 的 prompt 里也改成展示存量值。
- `outfits` 写 `outfit_items.layer` 时同样存量优先。

顺带一个行为变化：没填场合的单品，正式度从「等于目标值（距离 0）」变成「按日常 2 算」，在 work/formal 场合不会再被无脑优先。

### 详情弹层

- 图库卡片整块可点（`cursor-pointer`），删除按钮 `stopPropagation`，点删除不会同时开详情。
- 弹层：1024 那档大图 + 只读（品类、厚薄、created_at）+ 可编辑（颜色、品牌、材质、价格、正式度 1–5、层次、季节多选、备注）+ 保存 / 取消 / 删除（删除是按钮内二次确认）。
- 保存走 `PATCH /api/items/{id}`（本来就支持这些字段，补了一条测试钉住），成功后 `invalidateQueries(['items'])` 并关闭；角标 `信息不全` 只看 `color_family`，所以补颜色后角标会消失、筛选数量 -1。
- 表单 → body 的转换抽成 `core/itemPatch.ts`：空字符串转 `null`、没改的字段不进 body、价格/正式度做数字转换；价格非数字或 <0、正式度不在 1–5 时就地提示且不发请求。

### 验证

| 项 | 结果 |
|---|---|
| 后端 | **164 passed**（161 + 2 rules + 1 PATCH 全字段） |
| 前端 | **56 passed**（50 + 6） / typecheck 0 / build 0 |
| 真实接口 | `GET /api/items/{id}` 返回全部可编辑字段，`image.url` 是 `_1024.webp` 那档 |
| 浏览器点击（a–e） | **未执行**，需要你点 |

## 35. W6a：底部标签栏 + 移动端触控（2026-11-22）

- 顶部只留标题，导航改成底部固定标签栏：三项（📷 录入 / 🧺 图库 / 👕 搭配），图标在上文案在下，每项 `min-h-14`（56px）；选中项文字加粗 + 顶部 2px 指示线。
- 底栏用 `fixed inset-x-0 bottom-0 mx-auto max-w-xl`：手机上贴底、桌面下跟内容一起居中，不铺满整屏。
- 安全区：`pb-[env(safe-area-inset-bottom)]`，`index.html` 的 `viewport-fit=cover` 本来就有。
- `main` 加 `pb-24`（96px），最后一张卡片不会被底栏盖住；Toast 也上移到 `bottom-24`，否则会被底栏挡。
- 触控：图库删除按钮视觉仍是小胶囊，但用 `after:-inset-1.5` 把热区撑到约 36×44；`body { overflow-x: hidden }` 兜底，手机上不会左右滑。
- 录入页底部那排按钮改 `flex-wrap`，375px 下会换行而不是横向溢出。

**没做的**：暗色模式、字体缩放、动效（按范围）。视觉验收（375×667 / 390×844 / 桌面居中）需要在浏览器里点，agent 无浏览器。

## 36. W7a：录入预填（多模态 + 置信度弃答）（2026-11-22）

### 只做两件事

`POST /api/classify`（body `{image_id}`）只判断**品类**和**厚薄**，prompt 里明说不判断颜色/材质/品牌。理由见第 5 节的修订：这两步最耗时且最明显。

### 客户端

`llm.chat_json_with_image()` 与 `chat_json()` 共用 `_read_completion()`（重试去 `response_format`、429/5xx/截断/空正文/JSON 围栏都在那一处），差别只是 `content` 用数组形式 + `data:<mime>;base64,...`。

### 图片预处理

优先取 1024 展示图，用 Pillow `convert("RGB")` + `thumbnail(512)` + JPEG q80 再 base64。**不把原图发出去**：原图 3–5MB 会烧掉大量 token，而且可能带 EXIF。

### 闭合校验与弃答

| 情况 | reason | 返回 |
|---|---|---|
| 没有 key | `no_key` | 200，不调上游 |
| 品类不在六选一 / 厚薄不在 1-3 | `invalid_label` | 200，category/warmth 置 null |
| confidence 不是 0–1 的数字 | `invalid_confidence` | 200 |
| confidence < 阈值（默认 0.6，`EW_CLASSIFY_MIN_CONFIDENCE`） | `low_confidence` | 200，两个值都置 null |
| 超时 / 429 / 非 JSON / 结构不对 / 图丢了 | `timeout` / `rate_limited` / `bad_json` / `bad_structure` / `image_missing` | 200 |

**任何路径都不 500**：录入流程不该因为模型抽风而中断。

### 缓存与日志

- 结果按 `image_id` 缓存在进程内 dict，TTL 30 分钟；**只缓存成功结果**——失败不缓存，用户补了 key 能重试（否则 30 分钟内都被 no_key 卡住）。
- 日志只有 `image_id / source / reason / confidence / elapsed_ms`，不记 base64、不记完整响应。

### 验证

| 项 | 结果 |
|---|---|
| 后端 | **173 passed**（165 + 8） |
| 真实 HTTP（假上游）：无 key | 200 `no_key`，上游调用 0 次 |
| 真实 HTTP（假上游）：带 key | 200 `{category: shoes, warmth: 2, confidence: 0.88}`，发出去的图是 `data:image/jpeg;base64,/9j/`（JPEG） |
| 缓存 | 第二次调用上游仍只 1 次 |
| 真实模型分类 | **未执行**：agent 环境没有 key，也不该用用户的 key |

**你需要跑一次真实验收**（拿到真实置信度）：

```powershell
curl -X POST http://127.0.0.1:8000/api/classify -H "Content-Type: application/json" -H "X-LLM-Key: <你的key>" -d '{\"image_id\": 64}'
```

图片 id 64 是库里的一双鞋（`items.id=64`）。

## 37. W7b：录入页接上自动识别（2026-11-22）

### 流程变了

原来：选图 → 本地队列 → Enter 时才上传。
现在：选图 → **立刻上传**（拿 `image_id`）→ 立刻分类 → 给出建议；Enter 直接复用这个 `image_id`，不再重复上传。

必须保留旧路径：自动识别关掉、或上传失败时，退回「Enter 时才上传」。`Draft.uploadState` 就是干这个的（`idle → uploading → done | failed`）。

### 一次只跑一条

队列第一张才启动流水线，用 `pipelineRef` 记住正在处理哪张，避免同一张被 effect 重复触发；保存/跳过后新的第一张会自动接上（effect 依赖 `drafts`）。

### 用户选择优先

`core/capturePrefill.ts` 的 `mergeSuggestion()`：只填**空**字段，并标 `source='suggestion'`（UI 画虚框 + 「建议」角标）；用户按 1-6 / QWE 走 `chooseCategory/chooseWarmth`，`source='user'`，建议不再显示也不覆盖。
**Enter 时若用户没选，直接采用建议值**——这是「一次 Enter 就存」的关键。

### 暂存图的回收（三个出口）

- 保存成功：`image_ids` 直接用提前传的 id，不重复上传。
- 保存失败且图是提前传的：`DELETE /api/images/{id}`。
- 跳过：同样的 DELETE。

**顺手修了一个真 bug**：`DELETE /api/images/{id}` 原来只删 `path`/`thumb_path` 两张派生图，**tmp 里的原图留着**（`Image` 只记派生路径）。现在按 stem 把 `<stem>.*` 一并清掉。验收 c 实测：`tmp: 0 -> 3 -> 0`。

### 设置项

「录入时自动识别」开关在搭配页的设置弹层里（key 也那儿），存 `localStorage['ew.autoClassify']`，默认开。关掉后选图不上传、不分类，行为和 W7a 之前完全一致。

### 验证

| 项 | 结果 |
|---|---|
| 后端 | **174 passed**（173 + 暂存删除全清） |
| 前端 | **59 passed**（56 + 3） / typecheck 0 / build 0 |
| a) 无 key | 200 `{source: none, reason: no_key}` |
| c) 跳过 → 删图 | 上传后 tmp 3 个文件，DELETE 后 0 个 |
| 产物 | 含「正在识别」「建议」「录入时自动识别」「ew.autoClassify」 |
| b) 真模型返回 / d–g 交互 | **未执行**：需要你的 key 和浏览器 |

### 补丁：save 与上传流水线的竞态（2026-11-22）

**现象**：选图后立刻按 Enter，同一张图被上传两次，先传完的那张留在 `media/tmp` 成为孤儿。

**原因**：`save()` 只看 `current.imageId === null` 就自己上传，没有考虑「流水线正在上传中」这个中间态——此时 `imageId` 还是 null，但上传已经在路上。

**修法**：
- 新增 `uploadPromiseRef` 保存**在途上传的 promise**（解析为 image id，失败为 null），流水线发起上传时就写进去，结束清空。
- `save()` 走 `core/uploadOnce.ts` 的 `resolveImageId()`：已有 id 直接用 → 有在途就 `await` 它 → 都没有才自己传。顺序反过来就会双传。
- 保存成功后不再调 `DELETE /api/images`（图已归属单品，会 409），改用 `removeHead(false)`；跳过/失败才回收。
- 加 `consumedRef`：已被 Enter 保存掉的草稿，上传完成后不再花钱调分类。

**为什么没有渲染级测试**：本机的 vitest 渲染 React 会撞上重复 React 副本（hook dispatcher 为 null），`createRoot().render()` 直接抛错（第 17 节记过）。所以把决策逻辑抽成纯函数 `resolveImageId()`，用 3 条单测钉住：「已有 id 不上传」「有在途不上传」「在途失败才自己传」。React 状态时序本身仍需人工验。

**待人工验**：选图后立刻 Enter → `media/tmp` 应只剩 0 个文件，且 Network 里只有 1 个 `POST /api/images`。

## 38. W6b：对话入口（意图 + 工具链）（2026-11-22）

### 先抽 service

`routers/recommend.py` 的主体搬到 `recommend_service.build_recommendation()`，路由变成薄壳（解析参数 → 调 service → 设 `X-RateLimit-Remaining`）。**174 条既有测试一条没改，只改了 import**，这是这次重构唯一可信的验收标准。

新增参数 `exclude_ids`（在 `load_wardrobe` 里剔除），供「换一套」用；缓存 key 里的 `wardrobe_hash` 用过滤后的行，所以排除后不会误命中原结果。

### 意图解析

- 关键词先跑，顺序是 **weather → reroll → recommend**（「今天下雨穿什么」应算天气而不是推荐）。
- 场合词表覆盖四类；命中的词同时作为 `note` 进回复文案（「适合**约会**的搭配」）。
- 规则没解析出场合**且带了 key** 才问模型；模型的 `intent` / `occasion` 任一越界就整条丢弃、保留规则结果。任何异常都吞掉。

### 工具链

`TOOLS` 注册表 + `CHAINS` 按意图组装，每步返回 `(summary, payload)` 并记 `{tool, summary, ms}`：

| 意图 | 链路 |
|---|---|
| recommend | get_weather → search_wardrobe → build_outfits → validate |
| reroll | 同上（`exclude_ids` 同时作用于工具与最终结果） |
| weather | 只跑 get_weather |

**取舍**：工具链负责「可展示的执行证据」，最终 outfits 仍由 `build_recommendation()` 产出——否则模型、缓存、限流、指标要写第二遍。代价是多一次 DB 查询和一次规则组套（毫秒级，天气命中缓存）。

### 接口

`POST /api/chat`：`message` 空（strip 后）或 >200 字 → 422；`reply` 用模板，不额外调模型；天气意图返回空 outfits；天气上游失败仍按原语义 502（不吞成 200）。

### 验证

| 项 | 结果 |
|---|---|
| 后端 | **182 passed**（174 + 8） |
| b) 真实 `{"message":"我晚点要约会"}` | 200，reply「正在衣柜里为你挑适合约会的搭配」，trace 4 步，outfits 3 套 |
| c) `{"message":"今天天气怎么样"}` | 200，trace 1 步，outfits 0，reply 含实时温度与体感 |
| d) 不带 key | 200，`source=rules` |

### 观察：上游挂了时每个请求要 11 秒（已在 W6b-补 修掉）

验证时 Open-Meteo 正好连不上（TLS 超时，重试一次），每次请求都先撞 11 秒再回落到 DB 快照（`cache=db_stale`）。功能是对的，但体验很差——**每次都要重试上游**。

**修法（W6b-补）**：模块级 `_cooldown_until`（monotonic）。上游失败（超时/连接错误/5xx）后冷却 `EW_WEATHER_COOLDOWN_SECONDS`（默认 60 秒）；冷却期内**有兜底就直接返回 stale，不再打上游**。关键细节：**没有兜底数据时不进冷却**——否则首次请求会永远 502，用户永远等不到一次成功。

实测（上游指到一个只接连接、不响应的黑洞端口）：

```
request 1: 200 10589ms  stale=True   ← 两次 5s 超时
request 2: 200     3ms  stale=True   ← cooldown=1，不打上游
request 3: 200     2ms  stale=True
```

日志：`weather city=… cache=db_stale cooldown=1 elapsed_ms=0`。

冷却期内上游恢复了也不会提前重试——60 秒后自然恢复；成功一次即 `_cooldown_until = 0`。

## 39. W6c：对话页「问问」（2026-11-22）

### 卡片只留一份

把搭配卡片抽成 `ui/components/OutfitCard.tsx`（`outfit` + 可选 `onSave` / `saved` / `saving` / `onReroll` / `rerolling`）。搭配页传 `onSave`，对话页不传——**同一个组件，两种用法，不会长出第二套卡片样式**。

### 为什么这时才引入 zustand

之前一直没引入状态库，理由是「跨页共享状态为零」：每个页面自己 `useQuery`，tab 切走就卸载、切回来重新拉。现在对话历史必须跨 tab 存在（否则切去看图库再回来，聊天记录没了），这就是第一个真正的跨组件状态。用 zustand 而不是 Context：更新只重渲染订阅者，且不需要包 Provider。**刷新即清空**，不做持久化——聊天记录不值得为它上 localStorage 迁移逻辑。

### 对话页

- 消息：用户右侧深色气泡，agent 左侧浅色；失败时红底气泡 + 「重试」。
- agent 消息带 `trace` 时渲染 `<details>` 折叠条「执行了 N 步」，展开是 `工具 · 摘要 · 耗时`。
- 带 `outfits` 时渲染 `OutfitCard` 列表 + 一条「换一套」，`exclude_ids` 取当前第一套的 item ids。
- 输入区 fixed 在 tab 栏正上方（`bottom-[calc(3.5rem+env(safe-area-inset-bottom))]`），Enter 即发；发送中禁用并显示「正在挑…」。
- 空状态给三个示例问题。
- 有 key 走 `mode=llm`，没 key 走 `mode=rules`（服务端本来就会降级，这是双保险）。

### 底栏四个 tab

`grid-cols-4`，字号从 11px 降到 10px、图标 18→16px，`whitespace-nowrap` 防止「录入」被断行；375px 下每格约 93px，放得下。

### 验证

| 项 | 结果 |
|---|---|
| 前端 | **64 passed**（62 + 2 chatStore） / typecheck 0 / build 0（299KB / gzip 92KB） |
| 后端 | 187 passed（未回退） |
| 产物 | 含「问问」「执行了」「换一套」「正在挑」与示例问题 |
| d–g 真机交互 | **未执行**，需要你点 |

## 40. W8a：尺码 / 购买链接 / 洗护说明 / 洗护符号（2026-11-22）

### 为什么洗护符号要编码而不是自由文本

「30度」「30℃」「温水」三种写法会同时存在于一个用户的衣柜里，之后想按洗护方式筛选（比如「只显示能机洗的」）就没法做。所以只允许 12 个编码，前后端共用同一张表：

```
wash_30 / wash_40 / hand_wash / no_wash
bleach_ok / no_bleach
tumble_low / no_tumble
iron_low / no_iron
dry_clean / no_dry_clean
```

- 后端 `schemas.CARE_SYMBOLS` 是唯一权威；`ItemCreate` / `ItemUpdate` 用 `field_validator` 校验，出现表外值直接 **422**（不让脏数据进库）。
- `ItemOut` 出口也过滤一遍：就算库里被外部工具写脏了，API 也不会把它吐出去。
- DB 存 JSON 字符串（和 `season` 一样），对外永远是 `string[]`。

### 其它三列

- `size String(16)`、`purchase_url Text`（只限长 ≤ 500，不做格式强校验——用户可能贴的是淘宝短链或带参数的 URL）。
- `care_text Text` 存自然语言洗护说明，和符号互补：符号能筛选，文字能表达「反面晾干」这种符号覆盖不到的。

### 迁移

`c43a9b2d4cb9_item_size_purchase_care.py`，四列全部可空，用 `batch_alter_table`（SQLite 加列要重建表，batch 模式才安全）。

### 前端

详情弹层加了四个控件：尺码单行、购买链接单行（`http(s)://` 开头时下方给「打开链接」）、洗护符号 12 个可点标签（选中深色，空时显示「未填」）、洗护说明两行文本。`buildItemPatch` 已覆盖这四项——没改不出现、清空发 null。

### 验证

| 项 | 结果 |
|---|---|
| 后端 | **192 passed**（187 + 5） |
| 前端 | **65 passed**（64 + 1） / typecheck 0 / build 0 |
| 真实库 | `alembic head = c43a9b2d4cb9`，四列都在；PATCH 四项 → 重读一致；`wash_60` → 422；验证后已还原原值 |

## 41. W8b：截图识别 + 洗护符号互斥（2026-11-22）

### 互斥校验（后端 + 前端双保险）

五组互斥：洗涤方式、漂白、烘干、熨烫、干洗。后端 `_validate_care_symbols` 检查同组多选 → **422**，detail 写明冲突的是哪几个编码；前端把同组其他按钮**置灰不可点**（点了也顶掉旧的，`toggleCare` 里先剔除同组再追加），所以正常情况下用户碰不到 422。

### 截图识别

`POST /api/items/extract-receipt`（multipart，字段 `file`）：

- Pillow 压到最长边 768、RGB、JPEG q80 → base64；**不发原图**（截图动辄 2–4MB，白烧 token）。
- prompt 明确「这是购物 App 截图，只提这五项，看不清给 null，不要猜」。
- 闭合校验：`confidence` 不是 0–1 数字 → 整条弃答；低于 `EW_CLASSIFY_MIN_CONFIDENCE`（默认 0.6）→ 全部 null + `low_confidence`；`price` 非数字或 <0 → 只丢 price，其它保留；文本 trim 并截到 32 字。
- 无 key / 超时 / 非 JSON / 图坏了 / 太大 → **200 + source=none + reason**，绝不 500。
- 不落库、不绑定单品：这是建议值，用户确认后走普通 PATCH。

### 前端预填

`core/receiptMerge.ts` 的 `mergeReceipt(form, receipt)`：**只填当前为空的字段**，返回 `filled` 列表；被填的字段打「识别」小标记，用户一改标记就消失（`update()` 里清 `recognized`）。没 key 时按钮仍可点（会上传），结果位置显示「没配置 API key，暂时无法识别」；再下面一行小字「截图会发送给你配置的模型服务商」。

### 验证（真实 HTTP，模型侧是本地假上游）

```
d) conflicting care symbols: 422 | 互斥 in detail: True
   one per group: 200 ['wash_40', 'no_bleach', 'no_tumble']
c) no key: 200 {source: none, reason: no_key} | upstream calls: 0
a) with key: 200 {brand: 优衣库, price: 199.0, material: 棉, color_family: 藏青, size: M, confidence: 0.88}
   image prefix: data:image/jpeg;base64,/9j/4AA | has text part: True
```

| 项 | 结果 |
|---|---|
| 后端 | **203 passed**（192 + 11） |
| 前端 | **68 passed**（65 + 3） / typecheck 0 / build 0 |
| 真模型 + 真实截图 | **未执行**：没有 key，也不该用用户的 |

## 42. W10：详情弹层可改品类 / 厚薄 / 场合（2026-11-22）

之前这三个是只读的——可它们恰恰是推荐的三个核心输入（品类决定角色、厚薄决定温度匹配、场合决定筛选），录入选错就只能删了重录。后端 PATCH 一直支持，是弹层缺控件。

- 弹层最上面加三块（品类 6 个 / 厚薄 3 个 + 不填 / 场合 4 个 + 不填），顺序在其它字段之前。
- **品类不允许清空**（`items.category` NOT NULL），只能改成另一个；厚薄、场合可清空。
- `buildItemPatch` 只在值变化时才带上这三项：`category` 原样、`warmth` 转数字或 null、`occasion` 字符串或 null。
- 不新增校验：三个都是枚举选择，选不出非法值。

**缓存会自动失效**：LLM 结果的缓存 key 里含 `wardrobe_hash = hash(id:updated_at)`，改任何一个字段都会让 `updated_at` 变，下次请求自然 miss。实测同一批单品改完再算，hash 从 `29c69c149fef` 变成 `4b8a5f7c7b78`。

验证：前端 **71 passed**（68 + 3）/ typecheck 0 / build 0；真实接口 PATCH `occasion→work`、`warmth→null`、`category→outer` 都 200，验证后已还原原值；后端 203 条未动。

### 补丁：按品类决定显示哪些字段

`core/itemFields.ts` 的 `visibleFields(category)` 是一张显式的可见性矩阵：

| 字段 | 品类限制 |
|---|---|
| 恒显示 | category / occasion / formality / color_family / brand / price / purchase_url / note / material / care_text |
| warmth | 除 accessory 外都显示 |
| layer | 只有 top / outer |
| season / size | 除 accessory 外都显示 |
| care_symbols | top / outer / bottom / dress（鞋与配饰不显示） |

两条关键约束：

1. **隐藏 ≠ 清空**：表单值仍留在 state 里，只是不渲染。用户把「上衣」切成「鞋」再切回来，原来的层次和洗护符号还在。
2. **隐藏 ≠ 提交**：`buildItemPatch` 结尾按 `visibleFields(form.category)` 过滤一遍 patch，隐藏字段即便 form 里「看起来改过」也不会进请求——避免「切一下品类就把原值覆盖成 null」。

录入页顺手同步：选「配饰」时厚薄那一排直接不渲染，`Q/W/E` 快捷键也忽略（否则会往一个没有意义的字段里写值）。

**和原始需求的一处出入**：要求的测试「切到鞋后 warmth 不进 patch」与矩阵本身矛盾（warmth 对鞋是可见的）。所以落地的两条测试是：切到鞋后 **layer / care_symbols** 不进 patch；切到**配饰**后 **warmth** 不进 patch——两条都覆盖了「隐藏字段不提交」这个真正的意图。

验证：前端 **77 passed**（71 + 4 + 2）/ typecheck 0 / build 0；后端 203 未动。

## 43. W11：对话从「命令解析器」改成「有性格的助手」（2026-11-22）

### 一次调用拿三样东西

有 key 时不再「先规则解析 → 再单独问模型场合」，而是：工具链跑完（天气 / 衣橱 / 组套 / 校验）→ **一次模型调用**同时产出 `{reply, intent, occasion, item_ids}`。

消息序列：`system`（人设）+ 2 组 few-shot（一个推荐、一个闲聊）+ 最近 6 条历史 + 本轮 user（含天气摘要与候选池清单）。few-shot 用真实的 user/assistant 轮次，比塞在 system 里更不容易写成报告。

### 底线不变

- `intent` / `occasion` 越界 → 整条丢弃，走规则结果（`fallback_reason=invalid_intent`）。
- 需要推荐时 `item_ids` 必须过 `validate_selection` 的四条硬校验；不合格把问题回灌重出一次；仍不合格 → **规则结果 + 保留模型的 reply**（reply 里没有 id，是安全的）。
- `intent=chat` / `weather` 时 `item_ids` 必须为空，带了就忽略。
- 无 key / 模型失败 → 模板回复，200。

**不许模型用文字描述穿搭**：它只能给 `item_ids`，搭配一律由卡片展示——否则用户看到「配灰色西裤和乐福鞋」却不知道是哪件。

### 上下文

`ChatIn.history` 最多取 6 条，单条截到 200 字。前端从 chatStore 取（不含当前这条），「换一套」时上一轮 assistant 的话自然也在里面。

### 代价

- trace 多了一步 `model`（4 步工具 + 1 步模型）。
- 对话的模型调用**不写 llm_metrics**（那是 `/api/recommend` 的路径），指标面板不统计对话用量——已知缺口。
- 闲聊也会跑完 4 步工具链（因为模型可能把「推荐」改判成「闲聊」，池子得先备好）；天气上游挂了时，有 key 的对话会降级成「天气暂时取不到」继续走，不会 502。

### 验证

真实 HTTP（模型用本地假上游，按 prompt 里的候选池挑 id）：

```
[你好，今天好累] reply: 累就先别折腾了… | intent=chat | outfits=0 | trace 5 步
[我晚点要约会]   reply: 约会就穿松快一点… | intent=recommend | outfits=3 | model 35ms
                 first outfit ids 全在池内（池子 8 件）
[no key]         reply: 模板句 | source=rules | outfits=3
```

后端 **208 passed**（203 + 5），前端 **83 passed** / typecheck 0 / build 0。

## 44. W12：等待轮播 + 组不出套时的具体建议（2026-11-22）

### 等待文案

发送后到响应前，聊天气泡每 800ms 换一句：`翻衣柜中… / 看看今天冷不冷… / 三件里挑一件… / 再确认下搭配…`。

**不做百分比进度条**——那是编出来的信息，用户会当真。而且**只在这次请求真的会调模型时轮播**：无 key 的模板回复不到 50ms 就回来了，闪一下反而更差，那种情况还是显示「正在挑…」。

### 组不出套时不让模型写

模型在「凑不齐一套」时最容易说空话（「面试就穿那件上衣吧——可是根本没有合适的」）。所以推荐意图 + 最终 outfits 为空时，**丢弃模型的 reply**，用后端按真实件数拼：

```
正式的话你只有 1 件能穿的上衣、0 件下装、0 双鞋，还凑不齐一套。
要么先补下装，要么我按现有这些随便配一套给你看？
```

- 件数来自 `filter_usable`（已排除软删），不是估的。
- 该场合一件能穿的都没有时换另一句：「…一件能穿的都没有（N 件里都标给了别的场合）。可以把几件通用款的场合留空，或者先补几件。」
- `intent=chat / weather` 不受影响。

### 「按现有的配一套」

前端按钮发一句「随便配一套」，后端识别到 `RELAX_PHRASES` 就把场合放宽到 `None` 再跑一次（并有 key 时也不让模型改回的 occasion 覆盖）；仍组不出就照实说。

### 验证（真实 HTTP，模型用本地假上游）

```
[明天面试穿什么] reply: 正式的话你只有 1 件能穿的上衣、0 件下装、0 双鞋…
                 intent=recommend | outfits=0 | 用的是模型那句: False
[随便配一套]     outfits=3（原场合 formal 被放宽）
```

测试：**212 passed**（208 + 4），前端 83 / typecheck 0 / build 0。

## 45. W13：寒暄要像打招呼，不播报天气（2026-11-22）

三个问题叠在一起：「你好」被判成 weather、回复里报「8 到 16 度」、上来就报天气没有招呼。

- **意图层**：新增寒暄白名单（你好 / 您好 / hi / hello / 在吗 / 早上好 / 晚上好 / 谢谢 / 好的 / 收到），**优先于其它意图**；但句子里夹了天气词（含「冷/热/度/伞」）或推荐词（「穿什么」）就不算纯寒暄，仍走原解析——「你好，今天冷吗」确实是在问天气。
- 顺带补了「冷吗 / 热吗」两个天气词：原来只认「冷不冷」，这类问句会被判成 recommend。
- **prompt 层**：人设里加一条明确的措辞规则——日常寒暄用「有点凉」「雾蒙蒙的」，只有用户明确问多少度 / 冷不冷 / 下不下雨时才给数字；few-shot 补一组「你好」的标准答案，并要求不用 emoji。
- **降级层**：无 key 时 chat 意图给「你好呀，今天想穿点什么？」，不再套用「正在衣柜里为你挑…」的模板。

验证（真实 HTTP，模型用本地假上游）：「你好」→ chat、0 张卡片、回复不含数字；「今天多少度」→ weather、带数字；无 key 的「你好」→ 寒暄模板。

测试：**215 passed**（212 + 3）。

### 补丁：寒暄别每句念同一个天气稿

现象：连说「你好」「嗨」「哈喽」「谢谢」，回复都是同一句天气播报，只换了开头称呼。

只改 prompt：

- 加两条措辞约束：「寒暄不必每句都带天气，一半的情况只回应问候本身（『在的，需要我看看穿什么吗？』『不客气，随时喊我』），不要每句都用同一个天气句式收尾」；「如果上一轮已经提过天气，这一轮不要再复述同一个天气描述」。
- few-shot 补一组「谢谢 → 不客气，随时喊我。」（不提天气的范例）。

这类问题测不了硬指标（属于模型措辞），所以没有新增测试；215 条保持全绿。

**留下的问题**：「嗨」「哈喽」「早啊」不在寒暄白名单里（只认「你好 / 您好 / hi / hello / …」），这几句仍会落到 recommend 意图，靠模型的意图判断兜底——大多能出 chat，但不保证。

### 补丁 2：不臆测用户状态 + 寒暄变体入白名单

- prompt 加一条：「不要臆测用户的状态或情绪（不要说『累了』『辛苦了』『今天心情不错吧』这类），除非用户自己提到；不知道就只回应问候本身。」
- 同时把唯一一组带情绪词的 few-shot（`你好，今天好累 → 累就先别折腾了…`）换成 `在吗 → 在的，需要我看看穿什么吗？`——即使那组里「累」是用户自己说的，留在 few-shot 里仍会被模型当成「可以主动说累」的示范。
- 寒暄白名单补上 `嗨 / 哈喽 / 哈啰 / 早啊 / 早安 / 午安 / 晚安`，从「模型可能判成 chat」变成「一定判成 chat」。
- 加了一条确定性测试：这七个变体都解析成 chat，但「哈喽，今天穿什么」仍走 recommend（guard 词优先）。

测试：**216 passed**（215 + 1）。

## 46. W14：识别加颜色家族 + 历史补齐（2026-11-22）

### 为什么要它

所有新录入的颜色都是空的 → 每张卡都挂「信息不全」→ 这个标记因为「全都有」而失效。给它一个确定的值，标记才重新有意义。

### 固定枚举

`black / white / gray / beige / brown / blue / navy / green / red / pink / purple / yellow / orange / multi`（14 个）。理由和洗护符号一样：自由文本会让「藏青 / 深蓝 / navy」并存，以后按颜色筛选就没法做。prompt 里明说「只说家族色，不要猜色号、不要 hex；有图案/多色/看不清给 multi 或 null」。

### 逐字段容错（这轮最重要的改动）

原来整个响应校验不过就一起丢，导致「颜色判错 → 品类也没了」。现在分开处理：

| 字段 | 非法时 |
|---|---|
| category | 置 null，其它字段保留 |
| warmth | 置 null，其它字段保留 |
| color_family | 置 null，**category/warmth 照常返回** |
| confidence | 非法 → 整条弃答；低于阈值 → 三样全 null |

有任何字段非法时 `reason=invalid_label` 但仍然 `source=llm`，前端照常使用合法的那部分。

### 录入页

`Draft` 增加 `colorFamily`，保存时若识别给了值就写进 `create_item.color_family`。**录入页不加颜色按钮**——颜色是三项里最不影响推荐的一项，为它多一次点击不值得；用户也能事后在详情弹层补。

### 历史补齐

`scripts/backfill_colors.py`：找出 `color_family IS NULL` 且未软删的单品，逐张调 `classify.classify_path()`（直接调函数，不打 HTTP），每件 sleep 0.3 秒，只写 `color_family`。默认 dry-run。

实测（在 DB 副本上跑，避免假数据污染真库）：`将处理 3 件 → 成功 3 / 弃答 0 / 失败 0`，副本空颜色 3 → 0，真库仍是 3。

### 图库角标

日常浏览改成 8px 琥珀色小圆点（`aria-label="信息不全"`），只在「信息不全」筛选视图里才显示完整文字——否则一屏五个大胶囊太吵。

### 遗留

- 库里已有的颜色是中文（棕/灰/白/米白/草绿色…），识别产出的是英文枚举，两套值并存。补数据时没有统一迁移。
- `多色 → multi` 是 prompt 约定，模型可能直接给 null（弃答），两种都可接受。

## 47. W15：颜色词表统一成英文枚举（2026-11-22）

库里原本中英两套并存（`棕 / 灰 / 白 / 米白` vs `brown / gray / white`）。今天只是观感问题，但只要手填还能写中文，明天就会出第三种写法，按颜色筛选和统计直接失效。

**顺序很关键**：先迁移数据，再加校验。反过来的话，历史中文值会卡在新校验外面，连读都读不出来。

1. **迁移脚本** `scripts/migrate_colors.py`（默认 dry-run）：中文子串 → 14 个枚举之一，长的键先匹配（`米白` 不会被 `白` 吃掉），映射不到的置 null 留给 `backfill_colors.py` 重新识别。实测真库 46 条：`白→white 17`、`棕→brown 9`、`黑→black 8`、`灰→gray 5`、`蓝→blue 3`、`草绿色→green 1`、`米白→beige 1` 等，跑完非枚举值为 0。
2. **校验**：`ItemCreate` / `ItemUpdate` 的 `color_family` 用 `field_validator` 卡 14 个枚举或 null，中文直接 **422**（detail 里列出允许值）。**不校验就永远堵不住新写法。**
3. **出口过滤**：`item_to_out` 里只放行枚举，历史脏值（万一有）输出 null。
4. **前端**：详情弹层的颜色从自由输入改成下拉，选项是中文（`COLOR_LABELS`：黑/白/灰/米/棕/蓝/藏青/绿/红/粉/紫/黄/橙/花色），存英文枚举。

**遗留**：`白灰` 这种混色会被「白」先匹配成 `white`，语义上更接近 `multi`；迁移是一次性的，没有为这类复合词单独建表。

验证：后端 **223 passed**（219 + 4），前端 83 / typecheck 0 / build 0；真库迁移后非枚举值为 0。

## 43. 交付阶段的两次「本地绿、CI 红」（2026-11-22）

第一次把仓库推上 GitHub，两个 CI job 全红。两次原因都不在代码逻辑，而在**环境差异**——恰好是 CI 存在的意义。

### ① `.gitignore` 的 `data/` 吞掉了源码目录

**现象**：backend job 14 秒失败，`ModuleNotFoundError: No module named 'app.data'`（`routers/cities.py` 导入 `..data.cities`）。

**原因**：`.gitignore` 里为忽略仓库根目录的 SQLite 目录写了 `data/`。这个模式**匹配任意层级**同名目录，于是 `backend/app/data/`（`cities.py` + `__init__.py`）从第一天起就没进过仓库。本地测试全绿，因为文件就在磁盘上；`git status` 干净、`git add -A` 也不报错。

**修法**：改成根锚定的 `/data/`，再把 `backend/app/data/` 补提交。

**规矩**：`.gitignore` 里写 `data/`、`dist/`、`build/` 这类目录模式时，若不打算匹配全部层级，必须写成 `/data/`。验证方式：`git check-ignore -v <路径>` 会指出是哪一行规则命中的。

### ② CI 的 Node 版本比本地老，依赖起不来

**现象**：frontend job 18 秒失败，12 个测试文件全部 `[vitest-pool]: Failed to start threads worker`，根因链是 `undici@8.12.4/lib/interceptor/decompress.js:78` 抛 `TypeError: Cannot read properties of undefined (reading 'bind')`。

**原因**：`ci.yml` 写 `node-version: 20`，本地是 Node 24。undici 8 用到了 Node 22+ 才有的 zlib 接口，在 Node 20 上是 `undefined`，`.bind()` 直接崩——表现不是「测试失败」，而是**测试根本没跑起来**。

**修法**：`node-version: 24`、`pnpm/action-setup` 的 `version: 11`（与本地一致）。

**规矩**：CI 的 Node / pnpm 版本必须与开发机对齐，否则会出现「依赖装得上、但跑不起来」这种最难查的形态——install 那步是绿的，跑测试才炸。

### 共同点

这两类问题都有相同的三个特征：`git status` 干净、本地测试全绿、`git add -A` 不报错。**只有干净克隆才暴露**。

所以 CI 的价值不在「再跑一遍测试」，而在**复现别人的环境**：新机器、新版本、空目录。它也确实抓到了两个本地永远抓不到的问题。

### 附：这段排查里另外确认的两件事

1. **HTTPS 到 github.com 在本机会被重置**（`Recv failure: Connection was reset`，443 端口 8 秒超时），但 SSH 22 端口通（106ms）。改走 SSH（`git@github.com:...`）后推送正常。
2. README 的 CI 徽标只看**默认分支最新一次运行**，之前失败的历史记录不影响它；那些红灯反而是「发现问题并修掉」的证据，不建议删。

## 44. 「信息不全」口径：从单字段扩到核心字段（2026-11-22）

### 选了什么

「信息不全」（`incomplete=true` 筛选 + 图库角标）从**只看颜色**改为**核心字段缺失**：

- `color_family` 为空 → 不全（所有品类）
- `occasion` 为空 → 不全（所有品类）
- `warmth` 为空 → 不全，**仅限**有厚薄概念的品类（top / outer / bottom / shoes / dress）；配饰没有厚薄，不因 warmth 缺失被标红

`category` 创建时必填，永不参与判定。

### 为什么

旧口径（见第 7 节）只把没填颜色算作不全，导致一件没填场合、没填厚薄的衣服不会被标出来——和「信息不全」这个词的语义不符。场合、厚薄是搭配推荐的核心输入，缺了它们推荐质量会掉，应该逼着用户补。

标红数量会一下变多，是预期的：这两个字段不会被自动识别稳定填充（分类模型只判品类 + 厚薄，厚薄还会置信度弃答），多数旧单品会被标出来——正好推动补录。

### 规矩：口径定义在 4 处，必须一起改

这个口径在 **4 个地方**定义，必须保持一致，否则会出现「筛选芯片返回的列表」和「卡片角标」对不上：

1. 后端筛选 `routers/items.py` 的 WHERE
2. 后端测试 `tests/test_api.py::test_incomplete_filter`
3. 前端角标 `ui/pages/GalleryPage.tsx`（调 `core/itemFields.ts::isIncomplete`）
4. 本文件

只改前端角标不改后端筛选 = 同一个筛选下，有的卡片带角标却不在列表里，或反之——典型的只改一端导致的数据契约断裂。所以这次虽然任务约束是「只改前端」，E 项破例动了后端的 WHERE 与对应测试（query 参数名和返回结构不变，只改 WHERE 语义，不动 schema/API 契约）。

为避免前端逻辑漂移，把判定收敛成纯函数 `core/itemFields.ts::isIncomplete`，角标直接调用；后端用模块常量 `WARMTH_CATEGORIES` 镜像前端的 `WITH_WARMTH`，两边注释互相点名。

### 什么时候该推翻

如果将来「场合」也能被自动识别稳定填充，或者产品上决定场合 / 厚薄不该是必填核心字段，再收窄口径。推翻时记得 4 处一起改。


