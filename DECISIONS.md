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


