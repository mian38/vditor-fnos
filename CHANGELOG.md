# Vditor 编辑器（fnOS 应用）更新记录

> **📌 维护约定**
> 本文（开发者版）与用户版 `CHANGELOG_USER.md` 必须保持同步。
> **后续发布任何新版本时，需同时更新这两份更新记录。**

- **应用标识**：`com.mian38.vditor`
- **当前版本**：**1.1.5**（当前主线）
- **归档版本**：**1.2.0beta**（标签 `v1.2.0beta` / 分支 `archive/v1.2.0beta`，不再作为主线维护）
- **形态**：飞牛 fnOS 官方 `.fpk` 安装包（非 Docker：系统进程直接运行 Python 标准库后端，前端静态托管）
- **版本体系**：`4.0.x` 为早期 β 迭代线（产物文件名统一带 `-beta` 标识）；自 **1.0** 起进入正式版序列。

> 说明：本文按时间倒序排列，覆盖自首个 `.fpk`（4.0.0）到 1.1.5 的全部版本。

---

## 1.2.0beta

> **归档状态**：本版本于 2026-10-02 开发完成，2026-10-03 转为 beta 归档。
> 标签 `v1.2.0beta`、分支 `archive/v1.2.0beta`，**不再作为主线维护**，代码完整保留、可随时恢复。
> 主线已回退至 `v1.1.x`（1.1.4），后续基于 1.1.x 继续迭代。
> 1.1.4 的 Web 端功能与配置**完全不变**。
>
> ⚠️ **开发中曾附带的 `android/` 原生客户端已在归档前彻底移除**（源码 / 构建脚本 /
> 签名凭据 / 构建环境 / APK 产物全部删除）。`/api/m/*` 服务端能力**完整保留**，
> 供后续自行开发移动版时对接，详见 `docs/MOBILE_API.md`。

### 新增 · 移动端 API（15 接口全部实装）

**背景**：1.1.3 只在 `docs/MOBILE_API.md` 预留了接口规范，**服务端没有任何 `/api/m/` 路由**（调用得 404）。本版本逐个落地。

- 新增 `mobile_api.py`（纯逻辑模块，遵循项目既有「纯函数拆 `vd_util.py`」约定）：
  - 统一响应包 `ok()` / `fail()`，以 `_` 前缀内部字段（`_http`）携带状态码，输出前经 `strip_internal()` 剥离。
  - `ERROR_HTTP` 错误码 → HTTP 映射（10 码）；**未登记码降级为 `SERVER_ERROR` + 500**，避免端上无映射可依。
  - `take_str` / `take_int` / `take_paging` 参数校验：非字符串即非法、整数夹到 `[lo,hi]`、分页非法值回落默认。
- `server.py` 新增约 20 个方法 + `do_PUT` / `do_DELETE`（Web 端原本无这两个方法）。
- **鉴权与会话隔离**：新增 `MTOKENS` 字典与 Bearer Token 鉴权，与 Web Cookie 会话**物理隔离**，便于按客户端维度限流与吊销。空闲 30 分钟 / 绝对 8 小时，**不做 IP 绑定**（手机常在蜂窝与 Wi-Fi 间切换，绑定会造成误失效）。硬上限 2000 条，`_sweep_sessions()` 一并清理。
- **乐观锁**：`PUT /api/m/file` 支持 `if_version`，服务端当前版本 = 历史版本条数 + 1，不一致回 `FORBIDDEN`。
- **路径安全全部复用现有函数**，不另写一套：`safe_join` / `_safe_doc` / `_m_resolve_doc` / `_doc_asset_dir` / `_folder_note_path` / `_version_dir`。
- **上传复用** `is_denied_upload`（黑名单）与 `upload_headers`（强制下载 + CSP sandbox），大小上限读 `SETTINGS["upload_max_mb"]` 不写死。
- 15 个接口：health / auth login·logout·session / roots / files / file(GET·POST·PUT·DELETE) / file versions·restore / upload / settings upload / file assets，另有 `/api/m/asset/<name>` 供取回附件二进制。
- `docs/MOBILE_API.md` 由「预留规范」重写为「已实现」：标注真实字段、每接口补 curl 示例、补两处易踩空约定（同名文件夹不暴露为目录、无 `word_count` 的原因）、补 `is_denied_upload` 收完整文件名的坑。

**修复 · 登出幂等**（联调发现）

- `POST /api/m/auth/logout` 原先对已失效/伪造 token 回 401，与文档承诺的「幂等」语义矛盾。端上「token 刚过期就点退出」「重复点退出」是常态，回 401 只会弹出用户看不懂的报错。改为：**无论token 状态一律回 `ok: true`**（「当前无有效会话」就是「已登出」）。

### 移除 · 原生 Android 客户端（归档前）

> 开发中曾实装 `android/` Kotlin 原生客户端，现**彻底移除**，原因与范围记录备查。

- **删除**：`android/` 全部源码与资源（11 个 `.kt`、布局 / 菜单 / drawable / mipmap / values / xml）、`build.gradle` / `settings.gradle` / `gradle.properties` / `build_apk.sh` / `android/README.md`；根目录残留的 `build.gradle` / `gradle.properties` / `local.properties`；`releases/Vditor-1.2.0-*.apk`；`vditor-fpk/app/m.html`（WebView 专用编辑器页）与 `/api/m/editor` 路由。
- **清理构建环境**：`C:\android-toolchain`（JDK 17 + SDK 34 + Gradle 8.7 + keystore，1.0 GB）、`~/.gradle`（603 MB）、`~/.android`（3.4 MB）—— **合计释放约 1.6 GB**。
- **`/api/m/*` 服务端能力完整保留**，未删除或降级任何接口 / 路由 / 数据结构，供后续自行开发移动版对接。
- **失效引用已全量检索**：`com.mian38.vditor` 是飞牛 fpk 包名，属正确保留项，非 Android 残留。

### 新增 · 「API 接口对外输出数据」开关

- 设置项 `api_output`，**默认关闭**，标注「仅用于开发调试」。
- 关闭时受控的 12 个数据接口一律回 `API_OUTPUT_DISABLED`（HTTP 403）且不输出任何数据；`health` 与 `auth/*` 不受控（否则调试者连服务是否在线都无法确认）。
- **鉴权优先于开关**：未登录时照常回 `INVALID_TOKEN`，只有「已登录 + 开关关闭」才回 `API_OUTPUT_DISABLED`，避免未授权者据此探测「这台机器有没有开 API 输出」。
- 前端配置项 / 后端校验 / 持久化三者口径统一用 `is True` / `=== true` 严格布尔判定，防止字符串 `"false"` 被当成真值导致「界面显示关闭、接口照常输出」。
- 环境变量 `VDITOR_API_OUTPUT=1` 可在首次生成配置时覆盖默认值。
- 详见 `docs/MOBILE_API.md` §2.1。

### 修复 · 完整审计与精简（同版本内三次修订，版本号不变）

> 详见归档分支的 `CODE_REVIEW_1.2.0.md`。不改变对外功能与接口行为，仅加固与去重。

**High（未捕获异常导致连接直接断开）**

- `_read_json`（server.py）：`json.loads` 对 `[1,2]` / `"str"` / `123` / `null` 这类**合法 JSON 但顶层非对象**的输入同样解析成功，随后 20 处 `_json_body` 调用方按 dict 使用而抛 AttributeError，冒泡到 socketserver 后连接被直接断开、客户端收不到任何响应。已在唯一入口校验 `isinstance(obj, dict)`。
- `read_version` / `delete_version`（server.py）：内部裸写 `int(ts)`，而 `_api_restore_version` / `_api_delete_version` 直接把客户端可控的 `data.get("ts")` 传入，`"abc"` / `None` / `[1]` 均抛异常。已抽出 `_version_path()`，非法 ts 归一为 None（调用方按「版本不存在」处理）。

**Medium**

- `_m_asset`：附件整文件读入内存（上限可达 512MB）→ 改为复用 `_send_file` 流式返回。
- `/api/m/asset/` 的开关判定原先在 `do_GET` 里另写一遍 → 收敛到 `_m_output_off`（新增 `_M_DATA_PREFIX`）。
- `_api_backup` / `_api_backup_restore`：临时文件清理改为 `try/finally`，异常路径不再泄漏几百 MB 的临时包。
- `_send_favicon`：`/favicon.ico` 是未鉴权即可访问的公开路径，原先无异常处理，图标文件异常时连接断开。

**精简（行为不变）**

- 抽出 `_m_doc_target()`，收敛 5 处「取 root/path + `_m_resolve_doc`」样板（各自错误码按要求保留）。
- 抽出 `_apply_and_reply()`，合并设置保存与导入的重复回包逻辑。
- 拆分 `_build_backup()` / `_extract_backup()`，使临时文件清理能用 `try/finally` 兜住。
- `_m_get` / `_m_put` / `_m_delete` 中 9 处 `tok = self._m_require()` 的 `tok` 有 8 处未使用 → 去掉赋值。
- 删死代码：`_m_doc_detail` 的 `size_ =` 死赋值、`vd_util.MOBILE_API_PREFIX` 常量（无任何引用）。
- `mobile_api.py`：`import hashlib` 提到模块顶部；模块 docstring 里过时的方法名 `_dispatch_m_*` 更正为实际名称。

**产物**

| 文件 | 大小 | md5 |
| --- | --- | --- |
| `releases/com.mian38.vditor_1.2.0.fpk` | 4,526,487 字节 | `530e8e643815d441bcdabe76225a34a4` |
| `releases/vditor-nas-1.2.0.tar.gz` | 4,488,801 字节 | `0f879d44e615a7ba6edc6f4c13fcfcf6` |

### 修复 · `make_nas.py` 漏登记模块

- 新增 `SHARED_FILES` 漏了 `mobile_api.py`，生成的 nas 版`import mobile_api`会 **ModuleNotFoundError 起不来**。
- 根因：第 4 步的 `filecmp` 自检**只比对「已在列表里」的文件**，对「本该在却没在」的文件是盲的。
- 修复：把 `mobile_api.py` 加入 `SHARED_FILES`，并新增 `check_imports_covered()` —— 扫源码里的 `import` 语句，凡解析到同目录 `.py` 的都必须已登记，否则报错退出（退出码非 0）。已实测能捕获该场景。

### 测试

- **`test_mobile_api.py` 66/66**（9 段：A 健康检查与鉴权 / B 登录会话 / C 分区与列表 / D 文档CRUD / E 历史版本 / F 上传限制与附件 / G 异常边界 / H 登出 / I Web 端兼容性）。较上轮 65 项 +1：H3 语义随登出幂等修复而改写，并补 H3b 重复登出。
- **`test_android_e2e.py` 48/48**（9 段端到端）：模拟客户端真实调用序跑通「登录 → 分区 → 列表 → 新建 → 读取 → 保存+乐观锁 → 附件 → 版本回滚 → 删除 → 登出」，**逐字校验 `/api/m/` 各接口依赖的每个字段名** —— 服务端改字段而文档没跟上会立刻红。
- **`test_api_output_switch.py` 26/26**（新建，5 段）：默认关闭 / 经设置开启立即生效 / 持久化 / 落盘内容 / 环境变量覆盖。
- **`test_audit_v120.py` 66/66**（新建）：把本轮审计修复的两条崩溃路径与 4 条中危项逐条钉死（非对象 JSON、非法 ts、附件流式读取、开关判定收敛、备份临时文件、favicon 异常）。
- `test_smoke_pkg.py` **53/53**（含「server 版本 == manifest 版本」）。
- `test_audit114.py` 186/189；`test_v113.py` / `test_v114.py` 各 2 项、`test_v406~v411` 共 5 项失败，均为**版本号硬编码断言**（断言 1.1.1 / 1.1.4，而当时是 1.2.0）。**主线回退 1.1.4 后这 9 项已全部转绿**（`test_audit114` 189/189、`test_v113` 79/79、`test_v114` 37/37、`test_v406` 12/12、`test_v407` 17/17）。

> **测试脚本自伤修复（记录备查）**：`test_android_e2e.py` 最初把文档根目录环境变量写成 `VDITOR_DOC_ROOT`，而实际是 `VDITOR_DOC_DIR` —— 服务端**静默回落到 `vditor-fpk/app/docs/`**，测试数据写进了真实文档区（已清理）。现已改对，并加两道守护：① 断言分区路径落在临时目录；② 收尾后校验工作区 docs 目录无残留文件。

> **排障备查 · `subprocess.PIPE` 会让服务「假死」**：用 `subprocess.PIPE` 接长驻服务输出，管道缓冲区（约 64 KB）写满后服务端会阻塞在写日志调用上，表现为「进程活着（`poll()` 返回 None）但不再应答任何请求」，与「未捕获异常打挂服务」几乎一模一样，极易误判。正确做法：输出一律落文件。本机测试还需 `urllib.request.install_opener(build_opener(ProxyHandler({})))` 绕开环境代理。

---

## 1.1.5

> 本轮共8 项需求：图表渲染修复（2）、设置面板选项卡化与「状态与日志」（2）、安装引导文档分区落盘、默认端口 3838、会话失效提示、开源合规整改。
> 代码规模：`server.py` 1,908 → **2,000** 行（80,995 → 84,976 字节）、`index.html` 2,510 → **2,800** 行（127,420 → 147,543 字节）、`ui_style_v414.css` 500 → **560** 行（25,019 → 28,038 字节）。合计 +496 / −31 行。

### 修复 · 图表渲染（CSP `EvalError` 与 Graphviz 源码外露）

**根因一：ECharts 被 CSP 拦下（实测报错）**

- 现象：编辑器内图表报 `echarts render error: EvalError: Evaluating a string as JavaScript violates the following Content Security Policy directive because 'unsafe-eval' is not an allowed source of script: script-src 'self' 'unsafe-inline'`。
- 根因：ECharts 渲染器在运行时用 `new Function(...)` 动态生成渲染函数（已实测命中 `echarts.min.js`），而 `SEC_HEADERS` 的 `script-src` 只有 `'self' 'unsafe-inline'`，**不含 `'unsafe-eval'`** → 浏览器直接抛 `EvalError`。1.1.4 审计加固时逐项收紧了 CSP，图表即在那时失效。
- 修复：`script-src` 增加 `'unsafe-eval'`。**缓解边界明确写进代码注释**：`script-src` 仍限定 `'self'`，不放开任何外部脚本来源；`'unsafe-eval'` 只放开「字符串求值」这一项，不影响脚本加载来源。同块`font-src` 补 `'wasm-unsafe-eval'`（供 KaTeX 等可能的 WebAssembly 路径），`script-src` 的放宽是必要且最小范围的。

**根因二：Graphviz 渲染所需的 script 标签从未引入**

- 现象：dot 代码块只原样显示源码，不渲染成图。
- 根因：Vditor 的 `graphvizRenderAdapter` 通过 `document.getElementById("vditorGraphVizScript")` 读取 Graphviz 胶水脚本的 `src`，再用 `src.replace("viz.js", "full.render.js")` **反推**同目录的 wasm 渲染器，然后 `new Blob(["importScripts('...')"])` + `new Worker(r)` 构造 Worker 并调用 `Viz({worker})`。而 `index.html` **从未引入该标签** → `getElementById` 返回 `null` → 整条渲染链路在第一步就断了（`vditor/dist/js/graphviz/` 下的 `viz.js` 11,468 B 与 `full.render.js` 1,979,941 B 一直都在包内，只是无人引用）。
- 修复：在 `index.min.js` 之后补`<script id="vditorGraphVizScript" src="/vditor/dist/js/graphviz/viz.js">`，并把上述推导机制写入 HTML 注释，避免后续误删。
- 静态资源可达性已实测：两个 js 均能匿名GET 到 200（`/vditor/` 前缀已在 `PUBLIC_STATIC_PREFIX` 白名单内，无需额外放行）。

### 新增 · 「关于与帮助」选项卡与设置面板选项卡化

- 设置面板由**单页长表单**改为 **7 个顶级选项卡**：`pg-folders`（文件夹设置）/ `pg-security`（访问控制）/ `pg-version`（历史版本）/ `pg-upload`（上传设置）/ `pg-maint`（维护）/ `pg-appearance`（外观设置）/ `pg-about`（关于与帮助，本版本新增）。切换逻辑收敛为单个 `selectSetPage(id)`，无内容重复。
- **「关于与帮助」下设 3 个子选项卡**：
  - **帮助**：沿用原有 `#btn-word-help`（「？ 使用指南」）控件与其事件绑定，**仅迁移位置不改ID**，行为零变化。
  - **快捷键**：新增 `.kb-list` 表格，共 14 行 / 29 个 `<kbd>`，覆盖编辑器（`Ctrl+S` / `Ctrl+Z` / `Shift+Z` / `Ctrl+B` / `Ctrl+I` / `Ctrl+K` / `Alt+1` / `Alt+2` / `Alt+0` / `Tab` / `Enter`）与本应用（`Ctrl+S` 保存、`Esc` 关闭浮层、`Ctrl+Enter` 保存并关闭）。
  - **关于本应用**：应用简介 + `.kv-list`（`#about-version` 运行时注入版本号、Vditor 版本 4.0.0、开发人员 mian38、GitHub 仓库地址）。
  - **开源协议与法律声明**：本项目 MIT、ECharts Apache-2.0、**KaTeX 字体为 SIL OFL 1.1（非 MIT，单独标注）**、免责声明。
- `openSettings()` 改为每次打开重置回`pg-folders`，避免沿用上次停留的选项卡造成困惑。

### 升级 · 「登录日志」→「状态与日志」

- 新增 `GET /api/status`（需登录）→ `Handler._build_status()`，返回三段**纯只读**信息（不含任何密钥/ 口令 / 哈希）：
  - `app`：`APP_VERSION`、Python 版本、`sys.platform`、运行时长（新增模块级 `START_TIME`）、监听 host/port、`docRoots` 逐分区的 `exists` / `writable` 检查。
  - `network`：`client_ip(self)`（已按 `trust_proxy` 口径处理 XFF）、直连 IP、`isLan`、协议（经 `trusted_forwarded_proto`）、`isHttps`、`trustProxy` / `secureCookie` 开关。
  - `security`：`NEEDS_SETUP`、当前是否有会话、上传上限、版本管理 / 自动保存秒数。另附浏览器侧信息（UA、分辨率、语言、来源、referrer）。
- 新增 `GET /api/app-log`（需登录）→ `load_app_log(limit=400)`：读`APP_LOG_FILE` 末尾最多 `APP_LOG_MAX_BYTES = 512KB`，**倒序**返回 400 行，文件不存在时回 `exists=False` 而非报错。`APP_LOG_FILE` 优先 `TRIM_PKGVAR/vditor.log`，回退 `BASE_DIR/vditor.log`。
- 前端：`.kv-list` 列表 + 「刷新状态」按钮 + 「查看应用日志」按钮（`<pre id="app-log-box">`），与原「查看登录日志」**并列**；`dd.ok` / `dd.warn` 两档配色区分正常与异常项。切到 `pg-maint` 时自动 `refreshStatus()`。
- 新增 `fmtDuration(秒)` 把运行时长渲染为「N 天 M 小时」形式。

### 修复 · 安装引导「文档存储目录」不生效

- 现象：向导自定义路径后，安装完成该路径**不出现在左侧分区列表**中。
- 根因：向导 `doc_dir` 经 `install_callback` 落盘为 `cmd/main` 的 `VDITOR_DOC_DIR` 环境变量，而 `VDITOR_DOC_DIR` 在 `build_doc_roots()` 的优先级链中只是**最低一档的单目录回退**（`VDITOR_DOC_DIRS` > `TRIM_DATA_SHARE_PATHS` > `load_managed_folders()` >单目录）。当系统数据共享路径或已有 `folders.json` 生效时，该环境变量被完全忽略 → 表现为「配了没用」。
- 修复：向导新增 `doc_partition_name` 字段（默认「我的文档」），`install_callback` 在目录有效时**直接落盘为文档分区**——写入 `${TRIM_PKGETC}/folders.json`（`[{"name": 显示名, "path": 绝对路径}]`），与「设置 → 文件夹设置」读写的是**同一份配置文件**。已用 `grep` 判重避免重复写入。`doc_dir` 的 tips 同步改为说明「直接作为编辑器左侧的一个文档分区生效」。
- 端到端实测：`install_callback` 落盘后 `build_doc_roots()` 返回 `[{"id":"测试分区","name":"测试分区","path":"C://tmp//wiz_test//docs"}]`，分区如期出现。

### 修复 · 默认端口 9000 → 3838

- 变更点（8 处）：`server.py` 端口注释、`cfg = {"PORT": "3838"}`、`os.environ.get("VDITOR_PORT", cfg.get("PORT", "3838"))`；`vditor-fpk/manifest` 的 `service_port`；`vditor-fpk/wizard/install` 的 `initValue`；`cmd/install_callback` 端口回退值；`cmd/main` 与 `cmd/upgrade_callback` 的 `|| echo 9000)` 回退；`nas-template/config.env` 的 `PORT=`；`nas-template/install.sh`、`nas-template/README.md`、`README.md` 的全部端口表述。
- **自定义端口引导自检结论：本来就生效，无需修复**。链路为 `wizard/install` 的 `port` 字段 → `install_callback` 写 `${TRIM_PKGETC}/port` → `cmd/main` 读该文件 → 以 `VDITOR_PORT` 传给 `server.py`；`checkport=false` 亦不会因端口占用而失败。本轮仅统一了回退默认值（`|| echo 3838`）。

### 新增 · 会话超时主动提示

- 现象：一段时间未操作后服务端会话已过期，前端**任何操作都无反应也无反馈**，必须手动刷新网页才能重新登录。
- 根因：服务端对未认证请求**已正确返回 401 + `{"error":"unauthenticated"}`**，问题纯在前端——各处裸调 `fetch` 后从不检查 `res.status`，401 响应被当作正常结果丢弃，用户界面毫无变化。
- 修复：包装 `window.fetch`（`installSessionGuard()`），对匹配 `/api/` 的请求：命中 **401** 即调 `showSessionExpired()` 弹出遮罩层，含「因长时间未操作，已退出登录，需要重新登录」文案与「刷新页面并重新登录」按钮（另有「稍后处理」关闭）。`sessionExpiredShown` 保证只弹一次。
- **豁免名单**：`AUTH_EXEMPT = ['/api/login', '/api/setup', '/api/logout', '/api/auth/check']` —— 这四个接口的 401 属正常业务反馈（如密码错误、尚未初始化），若一并拦截会导致登录页刚打开就弹遮罩。`catch` 分支（网络中断）同样只对非豁免的 API 请求提示。

### 开源合规整改（与功能改动同批交付）

- **许可**：新建根`LICENSE`（MIT，Copyright (c) 2026 mian38，末尾附第三方组件不覆盖声明），并 `cp` 同步到 `vditor-fpk/` / `vditor-nas/` / `nas-template/`（4 份 md5 一致 `fec2e148be348c1747fbdf97a5000b48`）。
- **SPDX**：17 个 Python 源文件加 `# SPDX-License-Identifier: MIT`（`server.py` / `vd_util.py` / `make_nas.py` / `bump_version.py` / `build_fpk.py` / `check_css_clip.py` + 11 个 `test_*.py`）。**`vditor-fpk/app/vditor/LICENSE` 为上游 B3log 版权，永不改动**（md5 `2b8b72506e88b670cb125015ee285e90` 保持不变）。
- **第三方许可**：新建 `THIRD_PARTY_NOTICES.md`（15 个组件 + Vditor 版本指纹 + ECharts 的 Apache-2.0 §4(d) NOTICE 保留义务 + KaTeX 字体SIL OFL 1.1 例外）；补`vditor/dist/js/echarts/LICENSE`（Apache-2.0 全文 11,358 B）与 `echarts/NOTICE`（169 B）。
- **开源文档**：`README.md` / `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md`（Contributor Covenant 2.1 官方原文）/ `SECURITY.md` / `requirements.txt`（零依赖 + 实测标准库 import 清单）/ `.github/` 三件套（PR 模板、bug 报告、feature 请求，均为 YAML Form）。
- **manifest**：补 `author=mian38` 与 `homepage=https://github.com/mian38/vditor-nas`。
- **移出版本控制**（磁盘保留）：`.workbuddy/`（4 份 AI 私有记忆，含内部 commit hash）、`fnpack.exe`（3.8 MB 第三方二进制），并`.gitignore` 补 `*.log` / `.idea/` / `.vscode/` / `*.env.local` / `Thumbs.db` / `.DS_Store` / `*~` / `*.bak` 等。
- 应用本体合规复核结论：SPDX 齐全、上游 LICENSE 未动、5 份第三方许可文件齐全、无硬编码口令、`requirements.txt` 与实际 import 逐条核对一致。

### 验证

- **新建 `test_v115.py` 30/30**（12段：CSP 含 `unsafe-eval`、graphviz 两 js 可访问、设置面板 7 选项卡与 3 子选项卡、`.kb-list` ≥12 行、42 组标签配平、`/api/status` 三段字段与分区可读写、`/api/app-log` 倒序与 `exists`、未登录 401、版本号一致性）。
- **全量回归全绿**：`test_v115` 30/30、`test_audit114` 189/189、`test_v114` 37/37、`test_v113` 79/79、`test_v406` 12/12、`test_v407` 17/17、`test_v112` 30/30、`test_smoke_pkg` 53/53、`test_smoke_new` 17/17、`test_lan_login` 9/9 —— **合计 473/473**。
- 产物：`releases/com.mian38.vditor_1.1.5.fpk`（**4,527,135** 字节，md5 `a43b90dbaba074d866e2e81d7ecbbafb`）、`releases/vditor-nas-1.1.5.tar.gz`（**4,507,989** 字节，md5 `5f91455d06ee76e781459a9910b83450`，370 文件 / 27 目录）。
- fpk 包内校验：外层 22 条目，内层 `app.tgz` 371 文件；`LICENSE` / `echarts/LICENSE` / `echarts/NOTICE` / 上游 `vditor/LICENSE` 四份许可齐备，**无 `__pycache__` 混入**；`APP_VERSION = "1.1.5"`、`service_port=3838`、`author=mian38`、`homepage` 均正确；CSP 含 `unsafe-eval`、`/api/status` 与 `/api/app-log` 路由、`vditorGraphVizScript` 标签、`session-mask` 遮罩、7 个顶级选项卡（`data-page` 共 11 处）全部在包内就位。

> **踩坑备查 · 批量插 SPDX 必须先探测换行符**：`core.autocrlf=true` 但仓库内**换行符混存**（部分文件磁盘上是 LF）。首版脚本硬编码 `split(b"\r\n")`，对 11 个 LF 文件等价于「整文件当一行」，SPDX 被追加到了文件**末尾**（`sys.exit(main())` 之后）。已全部回滚重做，改为先抽样探测 `nl = b"\r\n" if b"\r\n" in raw[:200] else b"\n"`。跨文件批量改文本前务必先确认换行符。

> **踩坑备查 · `manifest` 子串匹配会误判**：`assert "homepage=" not in raw` 会被 `desc=` 值内明文命中，须按行精确匹配 `l.startswith(b"homepage=")`；且行尾可能带 `\r`，比较前要 `split(b"\r\n")`。

## 1.1.4

### 审计与精简（同版本内二次修订，版本号不变）

> 本轮为**同版本内的代码审计 / 精简 / 加固**，不改变任何对外功能、接口行为与配置兼容性。

**修复（High · 4 处请求体长度解析未保护）**
- 根因：`/api/upload`、`/api/favicon`、`/api/backup/restore` 三处直接 `int(self.headers.get("Content-Length", 0))`，**未做异常保护**。已登录态下若客户端发送非数字 `Content-Length`（如 `abc`），`int()` 抛未捕获 `ValueError` → 连接被直接断开（客户端只见空响应），并向 stderr 打完整 traceback。仅 `/api/save` 因 `_read_json` 外层已有 `try` 而幸免。
- 修复：新增统一入口 `_content_length(handler)`（解析失败/负数一律归一为 `0`）与 `_read_body(handler, limit)`（**带上限**读取，缺失/非法/超限一律返回 `b""`，绝不抛异常、绝不无上限读入内存），4 处全部改用。
- 复测：`abc` / `-1` / 空 三类非法长度 × 4 个接口共 12 组，均返回正常 HTTP 状态码，无断连、无 traceback。

**加固**
- `FAVICON_MAX_BYTES = 4MB`：此前 `/api/favicon` 走`MAX_BODY_BYTES`（64MB），现补上更贴合图标体积的独立上限。
- 路径分隔符切分口径收敛为 `vd_util.split_ext_tokens()`，由 `normalize_ext_list()` 与 `_apply_settings()` 的黑名单回显共用，消除两处切分逻辑不一致的隐患（`_SEP_RE` 严格保持 `[，,; ]`，**不引入换行**，与旧行为逐字节等价）。

**精简**
- 删除死函数 `_env_bool`（AST 全量扫描确认 0 处引用，实际生效的是 `_bool_default_true`）。
- 清理 **13 个未使用 import**：`mimetypes`、`unquote`、`EXTRA_MIME`、`STATIC_DENY_NAMES`、`STATIC_DENY_EXTS`、`CACHE_MAX_AGE`、`UPLOAD_MAX_AGE`、`UPLOAD_INLINE_EXTS`、`UPLOAD_SANDBOX_EXTS`、`_http_date`、`parse_data_share_paths`、`read_share_paths_file`（`UPLOAD_NAME_RE` 经核查仍在用，保留）。
- 删除 3 行空占位分节注释，合并为 `# 响应安全头 / 缓存策略`。
- 抽取 6 处重复逻辑为公共入口：`_build_headers()`（`_send`/`_send_file` 两处 `SEC_HEADERS` + `Set-Cookie` 合并）、`_fail_entry()`（`is_locked`/`record_failure` 的滑动窗口口径）、`_json_body(err)`（12 处 `try: _read_json / except: 回 400` 样板）、`_apply_int_setting()`（3 个整型设置字段的校验骨架）、`split_ext_tokens()`、`_paths_from_json()`（两处 JSON 解析分支）。

**审计结论（无需处置的部分）**
- **零第三方依赖**，纯 Python 标准库 → 不存在依赖漏洞面。
- 无 `eval` / `exec` / `pickle` / `subprocess` / `os.system`；无硬编码密码、密钥、内网地址。
- 路径处理统一走 `safe_join()`；静态资源走 `PUBLIC_STATIC_EXACT/PREFIX` 白名单 + `is_static_denied()` 兜底；备份恢复对 tar 成员做 `..` 检查。
- `index.html`（2,510 行）无 `console.*` / `debugger` / `TODO`；18 处 `innerHTML` 中服务端数据（登录日志 IP、历史版本 diff、storage_path）全部经 `escapeHtml`，`cls` 来自固定分支，`info[0]` 来自固定白名单 → 无 XSS 缺陷。
- **包体无水分**：`vditor/` 占 98.5%（360 文件 / 15,385,064 字节），大头为 Vditor 官方运行时（lute 3.74MB、mermaid 3.57MB、graphviz 1.98MB、highlight 1.05MB、echarts 1.03MB 等），经核实全部为功能必需（`viz.js` 是 graphviz wasm 胶水、`third-languages.js` 是代码高亮第三语言包，均由 `index.min.js` 运行时动态加载），**不可删**。

**验证**
- **全量回归 `test_audit114.py` 189/189**（新建，12 段：A CLI/环境变量/配置、B 认证会话、C 文档CRUD、D 上传、E 历史版本、F 设置、G 文件夹、H 备份恢复、I 静态资源与安全头、J 异常与边界、K 纯函数单元、L 代码卫生）。
- `test_v114.py` **37/37**、`test_v113.py` **79/79**、`test_v112.py` **30/30**、包内冒烟 `test_smoke_pkg.py` **53/53**。
- 产物：`releases/com.mian38.vditor_1.1.4.fpk`（**4,516,769** 字节，较审计前 4,521,423减 4,654）、`releases/vditor-nas-1.1.4.tar.gz`（**4,470,136** 字节，368 文件）。
- 代码规模：`server.py` 1,910 → **1,906** 行（80,285 → 80,936 字节）、`vd_util.py` 417 → **435** 行（16,192 → 16,964 字节）、`index.html` 2,510 行**未改动**（127,420 字节）。

### 功能修复（同版本内首轮）

**修复（#1 黑名单行按钮错位）**
- 根因：设置区通用规则 `.set-sec button.action { margin: 10px 8px 0 0 }`（特异性 0,2,1，位置在后）为所有操作按钮加了 10px 上边距；1.1.3 在 `.set-ext-row button`（0,1,1）上写的 `margin: 0` **特异性不足，被通用规则压过**，导致「添加」「恢复默认」两个按钮整体下沉 10px，与输入框错位。
- 修复：把重置规则提高到 `.set-sec .set-ext-row button.action { margin: 0; white-space: nowrap; }`（0,3,1）。**关键是特异性而非顺序**——即使该规则排在通用规则之前也照样胜出，已在 `ui_style_v414.css` 注释中写明这一点。
- `apply_style_v414` 的 MUST 断言新增该规则，防止后续改动再次把按钮压下去。

**修复（#2 恢复默认后无法保存）**
- 根因：默认黑名单含 `appref-ms`（含连字符），而 `_EXT_TOKEN_RE`（`vd_util.py`）与前端 `denyTokenValid`（`index.html`）均为 `^[A-Za-z0-9]{1,12}$` → 点「恢复默认」后该项被判不合法、被 `normalize_ext_list()` 丢弃 → `_apply_settings()` 产生 errs → `_api_settings_update` **整次设置保存被拒**。
- 修复：三处校验同步放宽为 `^[A-Za-z0-9][A-Za-z0-9-]{0,11}$`（字母开头，可含连字符，1–12 位），前后端错误文案同步改为「需字母开头，仅含字母 / 数字 / 连字符，1–12 位」。默认清单 68 项可原样保存。
- **连带修复**：`UPLOAD_NAME_RE` 同样不接受连字符，含 `-` 的扩展名落盘后 `GET /<uuid>.appref-ms` 会 404（上传成功但文件取不到）。同步放宽为 `^[0-9a-f]{32}\.[A-Za-z0-9][A-Za-z0-9-]{0,11}$`。
- 非法项仍然照常拒绝：`../bad`、13 位超长、纯 `-`、前导 `-` 均被丢弃并在错误提示中列出。

**验证**
- 定向回归 `test_v114.py` **37/37**（按钮对齐 CSS 静态断言 / 特异性比较、恢复默认后保存成功且 `appref-ms` 落库、连字符扩展名被黑名单命中与移除后可上传且落盘文件可 GET（200 + `attachment` + CSP sandbox）、非法项仍拒、`vd_util` 纯函数边界、版本号一致性）。
- `test_v113.py` **79/79**、`test_v112.py` **30/30**、包内冒烟 `test_smoke_pkg.py` **53/53**。
- 首轮产物 `releases/com.mian38.vditor_1.1.4.fpk`（4,521,423 字节）→ 审计后重打包 **4,516,769 字节**。

---

## 1.1.3

**修复（#0 根因）**
- **「上传限制放开 + 可调」此前实际未生效：1.1.2 把 Vditor 上传的 `upload.accept` 设为 `'*'`（`index.html` 初始化与 `applyUploadSettings()` 两处）。但 Vditor 的类型校验实现为
  `accept && accept.split(",").some(t => t[0] === "." ? ext === t : mimeTop === t)`，**没有 `*` 分支**：`'*'` 不以 `.` 开头 → 落入 MIME 分支 → `"image" === "*"` 恒假 → 任何文件都被判类型不符；**`accept: ''` 同样失败**（`accept && …` 短路为假值，随即进入 `||` 报错分支）。故 1.1.2 的所有上传在浏览器端被全量拦截，服务端校验根本走不到。
- 修复方式：不再用 `accept` 表达限制，改为传入 `VDITOR_ACCEPT_ANY`（`split()` 返回 `some()` 恒真的对象）短路 Vditor 的类型校验，**格式判定统一交给服务端黑名单**。`upload.max` 仍由 Vditor 每次上传时实时读取，设置改动即刻生效。
- 修复**清空黑名单后又被默认清单还原**：`deny = SETTINGS.get("upload_deny") or DEFAULT_UPLOAD_DENY` 与 `if not _deny …→ 默认` 两处把「配成空」与「没配过」混为一谈，导致「删除全部条目」无效。改为**以键是否出现**判断（`load_settings()` 新增 `has_deny_key`，运行时用 `.get(k, default)` 而非 `or`），前端同样由 `('upload_deny' in SETTINGS_UI)` 判断。
- 修复 `test_v112.py` 中 2 项已被本版语义取代的断言（白名单语义），改为黑名单语义后该套件 30/30 通过。

**上传格式反转为黑名单（#2）**
- 新增 `DEFAULT_UPLOAD_DENY`（`vd_util.py`，67 项）：Windows 可执行 / 脚本 / 加载项、各类脚本与解释器代码、可在浏览器或本地执行 / 主动加载的内容（`html/htm/svg/xml/php/…`）。
- 新增 `normalize_ext_list()` / `is_denied_upload()`：仅字母数字、1–12 位，大小写不敏感，支持逗号 / 空格 / 分号 / 中文逗号分隔，非法项丢弃。
- `DEFAULT_SETTINGS` 增 `upload_deny`；`_handle_upload` 改以 `is_denied_upload()` 为**唯一校验依据**（`allow` 白名单分支删除）。
- `_apply_settings()` 逐项回显被丢弃的非法条目（如 `waytoolongnamehere`），不再静默吞掉。
- `_api_settings_export` keys 增补 `upload_deny`。

**向后兼容**
- `load_settings()`：`upload_deny` 键不存在（≤1.1.2 老配置 / 全新安装）→ 填默认黑名单；键存在即以用户值为准（可为空串 = 不限制）。
- 旧字段 `upload_accept` **保留在 settings.json 与导出中但不再参与任何校验**，仅供降级回 1.1.2 时还原。

**界面统一（#1）**
- 根因：`#set-upload-accept` 不在通用输入框样式选择器内（`ui_style_v414.css` 的 `#login-card input, .set-num input, .set-pw input…, .frow input, #set-page-title, #set-favicon`），故渲染为浏览器默认外观，与同页其它控件不一致。
- `.set-ext-row input` 已并入**基础 / `:focus` / `::placeholder` 三组选择器**，与同页输入框完全一致。
- 黑名单改为可逐条增删的 chip 形式（`.set-ext-chip` + 删除按钮），配「添加 / 恢复默认」；`#upload-deny-err` 并入 `#pw-err, #folders-err` 同一条校验反馈样式。
- `apply_style_v414` 的 MUST 断言新增 3 条（`.set-ext-row input:focus` / `.set-ext-chip` / `#upload-deny-err`）。

**移动端 API 预留（#3）**
- 新增 `docs/MOBILE_API.md`：15 个接口定义（健康检查、Bearer Token 鉴权 / 注销 / 会话、分区、列表、详情、新建、保存、删除、历史版本 / 回滚、上传、附件列表、上传限制只读查询）、统一响应包与 9 个错误码、接入注意事项、6 项待确认事项。
- `vd_util.py` 新增 `MOBILE_API_PREFIX = "/api/m/"` 占位常量。**当前无任何路由挂在此前缀下，调用返回 404**（仅规范，未实现）。

**验证**
- 定向回归 `test_v113.py` **79/79**（默认黑名单拦截 / 放行、增删条目、清空清单、老配置迁移、重启持久化、前端与样式静态断言）。
- 包内冒烟 `test_smoke_pkg.py` **53/53**。
- `test_v112.py` **30/30**。
- 产物 `releases/com.mian38.vditor_1.1.3.fpk`（4,520,205 字节）。

---

## 1.1.2

**上传（#2）**
- 解除前端 10MB 默认上限与固定格式白名单：默认不限制上传格式（HTML / JS 等危险类型仍由服务端**强制下载 + CSP 沙箱隔离**，不会被当作可执行脚本运行）。
- 新增「上传设置」：可分别设定**单个文件大小上限（1–512MB，默认 256MB）**与**允许的文件扩展名白名单**（留空 = 不限制）；服务端 `_handle_upload` 强制校验，前端 Vditor 同步 `upload.max` / `upload.accept`。

**网络安全策略（#3 / #4）**
- 「网络访问安全」两项（信任反向代理、强制 Cookie Secure 标记）**默认开启**；手动关闭需**二次确认**，并刷新了说明文案。
- 修复「`secure_cookie` 关闭后公网 HTTP 仍 401」的问题：关闭「强制 Cookie Secure 标记」后，登录凭证 Cookie 不再被强制加 `Secure` 标记，公网 HTTP 登录后可正常使用（此前因浏览器拒绝发送 Secure Cookie 而 401）。开启时仍保持「非局域网 HTTP 一律拦截」的安全行为（回归验证通过）。

**界面文案（#5 / #6 / #7）**
- 外观设置「暗黑模式」改名为「深色模式」，说明移至选项下方（深色模式即刻生效、无需保存、跟随系统、同步 Vditor 编辑器主题）。
- 网页图标下方说明更新为：「此处仅控制前端网页标题与图标，fnOS 内显示的本应用名与图标不受此处影响。」
- 卸载引导文案重写：明确「是否清除数据以应用内设置为准、Markdown 文档文件无论如何都不会被删除」。

> 说明：#0（Cloudflare 穿透下 304 表现）经核查为**源站机制正常**——`index.min.js` 显示 200 是 Cloudflare 边缘缓存静态资源所致，域名根 `/` 显示 304 是因为 HTML 不被边缘缓存、回源后命中条件请求；#1（5 分钟清理与会话锁定 15 分钟）经核查**二者不冲突**——定期清理只删除「锁定已过期且首败超时」的计数，活跃 15 分钟锁定完整保留。两项均无需改代码。

## 1.1.1

**安全**
- 上传物按类型决定响应方式：图片 / 音频 / 视频 / PDF 正常内联；其余（含 HTML / JS / XML 等可执行内容）一律**强制下载并附加 CSP 沙箱** —— 消除「上传的 HTML 被同源打开执行脚本」的存储型 XSS（该页可携带登录态调用全部 API）。
- `X-Forwarded-Proto` 仅在直连来源为**本机 / 局域网**时才信任，防止伪造该头绕过「强制 HTTPS」的页面级拦截。
- 静态文件服务由「**黑名单拦截**」改为「**白名单放行**」：仅 `/index.html`、`/vditor/`、`/ui/` 可被公开访问，其余路径一律 404 —— 黑名单依赖「穷举危险文件名」，一旦漏配即暴露；白名单默认拒绝，更可靠。

**稳定性**
- 所有接口增加**请求体上限**（普通 64MB / 上传 256MB / 恢复备份 512MB），超限直接返回 413，避免超大请求占用内存。
- 修正**历史版本目录键编码**：旧的「用 `__` 拼接相对路径」会让 `a/b__c.md` 与 `a__b/c.md` 混用同一版本目录（历史版本互相串用）；现改为「可读前缀 + 路径哈希」，并**自动迁移**既有目录。
- 会话与登录失败计数新增**定期清理**（5 分钟一次 + 硬上限），防止长期运行内存缓慢增长。

**性能**
- 静态资源与上传物增加 `ETag` / `Last-Modified` / `Cache-Control`，支持 **304 复用**（此前每次打开页面都会重新下载全部前端资源）。
- 文件列表（2 秒）与上传物查找（30 秒）增加缓存，写操作即时失效。
- 备份导出改**流式写盘**、恢复改为**流式接收与解包**，显著降低大库场景的内存峰值。

**工程（可维护性，对功能无影响）**
- 「通用 Linux 部署版」（`vditor-nas/`）改为由 `vditor-fpk/app` **自动派生**（`make_nas.py`：共享文件 + NAS 专属模板组装），不再手工维护；回归测试也改为直接以 `vditor-fpk/app` 为运行目标 —— 从根本上消除「两份后端代码必须逐字节一致」的漂移隐患。
- **后端模块拆分**：`server.py`（2117 行）中无副作用的常量与纯函数抽出为 `vd_util.py`（346 行，`server.py` 降至 1863 行）。可变状态（`SETTINGS` / `SESSIONS` / `DOC_ROOTS` / `PWHASH`）仍留在 `server.py`，避免跨模块状态共享。同时在 `server.py` 顶部自举 `sys.path`，保证被 `python3 -c "import server"` / `-m` 等方式拉起时也不会 `ImportError`。
- **新增包内资源冒烟测试** `test_smoke_pkg.py`（53 项）：校验交付必需的 33 个静态资源可访问、13 个已移除 / 禁止路径返回 404（含 `server.py`、目录穿越、`mathjax`、`en_US.js`）、前端关键标记存在、ETag/304 生效、`server` 与 `manifest` 版本号一致。防止「改静态服务或精简包体时误删 / 误放行」。
- **新增版本号一键同步** `bump_version.py`：一次命令同步 `manifest` 的 `version=`、两处 `APP_VERSION` 及 `test_v406/407` 的硬编码断言（支持 `--dry-run`）。
- **回归结果**：135 / 135 通过（7 个脚本）。安装包 **4.51MB**。

---

## 1.1

**修复**
- 修复**文档迁移叠加**的重大缺陷：旧式扁平文档在「打开」时会被重复迁移，多次卸载重装后叠加成多层同名文件夹（如 `…/X/X/X/X.md`）。现迁移前先判断「是否已在同名文件夹内」，杜绝再次嵌套（已实测：同一文档重复打开 5 次路径保持不变）。

**变更**
- 「正文字数」统一按**预览口径**统计（改用 `vditor.getHTML()` 的渲染结果），切换编辑模式不再改变数值。

**优化**
- 代码审计与包体精简：删除运行时不引用的 `icons/material.js` 与非 `zh_CN` 语言包，清理空目录与冗余代码；安装包进一步减小。

**新增**
- 工具栏在「任务列表」之后新增**减少缩进 / 增加缩进**（outdent / indent）。

---

## 1.0.3

**新增**
- 工具栏收纳：「切换编辑模式 / 代码块主题预览 / 内容主题预览 / 导出 / 开发者工具 / 关于 / 帮助」7 项收进末尾的**「更多」子菜单**，常用区更短（保留全屏、大纲、预览）。

**修复**
- 修复正文字数**恒为极小值（极端情况恒为 2）**：此前按当前模式取渲染节点时，误取到被 CSS 隐藏的 `.vditor-preview` 残留容器（其中仅剩预览操作栏的少量文字）。现按当前编辑模式选取可见内容节点，跳过隐藏节点并剔除操作栏文字。

---

## 1.0.2

**修复**
- 修正「正文字数」口径：改为统计**渲染后读者实际可见**的字数（1 个中日韩表意字符记 1 字，连续的拉丁字母/数字记 1 个词，即外文 1 词 = 1 字）。不再沿用 Vditor 内置按编辑区文本节点长度计数的方式（那会把隐藏语法标记、代码与图表源码一并计入，导致正文虚高数倍）。
- 工具栏「大纲」按钮在窄屏（≤520px）可直接折叠 / 展开大纲侧栏（Vditor 原生开关含宽度门限，窄屏点了无反应，现已兜底接管）。

---

## 1.0.1

**变更**
- **移除**「卸载向导实时反映状态」功能并清理相关代码（实测该文案无法实时更新；是否清除数据仍由「设置→维护」开关经 `uninstall_callback` 决定）；卸载向导改为固定说明文案。
- 忘记密码提示统一为「请在 fnOS 终端中执行命令：`vditor reset-password`，按指引重置密码」；该命令的输出文案同步更新。

**新增**
- Vditor 顶栏新增**「预览」**控件（与既有「大纲」并列）。
- 编辑区**默认内容**改为 Markdown 教程（Vditor 官方 demo 预置示例，涵盖语法指导、列表、表格、数学公式、脑图、流程图、时序图、甘特图、图表、五线谱、Graphviz、脚注与快捷键）。

---

## 1.0（首个正式版）

**安全**
- 静态文件服务新增黑名单：拒绝以公开资源形式暴露后端源码与配置/密钥文件（`*.py`、`config.env`、`settings.json`、`login_log.json`、`folders.json`、`excluded.json`、`pwhash` 等）。
- 登录日志中的客户端 IP 渲染做 HTML 转义，消除经 `X-Forwarded-For` 注入的存储型 XSS。
- 登录 / 首次设置 / 修改密码接口对畸形 JSON 请求体做健壮处理（返回 400 而非 500）。
- 开启「强制 Cookie Secure」后，经**非局域网 HTTP** 访问不再返回应用页面（直接给出「需要 HTTPS 访问」提示页）——避免用户在明文 HTTP 上输入密码而被抓包。

**优化（包体精简 −27%）**
- 移除运行时未被引用的组件：MathJax（本应用固定使用 KaTeX，MathJax 分支不可达）、Vditor TypeScript 源码（`src/ts`）与类型定义（`dist/ts`、`types`、`*.d.ts`）、Vditor 开发版 `index.js` / `method.js`。安装包由 4.0.17β 的约 6.18 MB 降至约 4.51 MB。

**功能增强**
- 「导出备份」升级为**完整快照**（含配置、文档、上传物与历史版本），并新增**一键导入恢复**。
- 新建文档采用**「每文档一个同名文件夹」**结构；上传的图片 / 音频等与文档放在同一文件夹（文件管理器中可见、可随分区备份），并以**相对文档的路径**引用（导出后可离线直接打开）。
- 导出 `.md` / `.html` 时，若文档文件夹内存在其它文件，则自动将整个文件夹**打包为 zip** 导出。
- 打开旧式扁平文档时自动迁移为「同名文件夹」结构。

**界面**
- 设置界面重构：「维护」拆分为「备份与恢复 / 登录日志 / 卸载时的应用数据处理」三个子选项卡；「安全设置」前两项归入「网络访问安全」子选项卡；文件夹设置与安全设置说明文案优化。
- 修复设置子选项卡内开关复选框被整行输入框样式污染（被拉宽、文字换行）的问题。

**修复**
- 「信任反向代理」的 `X-Forwarded-For` 防伪造加固改为**可选严格模式**（`VDITOR_TRUST_PROXY_STRICT=1`），默认恢复原行为，避免经反向代理 / 内网穿透访问时 HTTP 登录的局域网判定异常。

---

## 4.0.17（β）

- **修复录音**后编辑器变灰无法编辑：录音停止即恢复编辑区可编辑，并把音频类型（`.wav/.mp3/.ogg/.m4a`）纳入上传白名单，录音可直接以 `<audio>` 嵌入文档播放。
- **字数统计升级为双口径**：顶栏同时显示「正文字数（不含 Markdown 语法）」与「含语法字数」，并新增「预计阅读时间约 x 分钟」。
- 移动端下拉菜单修复增强：把已显示的下拉面板脱离工具栏滚动容器、以 `position:fixed` 浮层覆盖在编辑区之上；字数统计移入顶栏同行显示。

## 4.0.16（β）

- 修复暗黑模式下登录对话框仍是浅色（登录卡片底色写死 `#fff`，改为随主题变量）。
- 重修移动端下拉菜单仍不弹出：把 `.vditor-panel` 从工具栏滚动容器中脱离并挂载到 `body` 后再 `fixed` 定位，并补上点击触发源。
- 顶栏新增**主题切换按钮**（🌙 / ☀️），与「设置 → 外观设置」的暗黑模式开关双向同步。
- 启用 Vditor 字数统计（`counter`）。
- 修复录音不可用：非安全上下文（HTTP）下不渲染录音按钮并提示改用 HTTPS。

## 4.0.15（β）

- 修复移动端下拉菜单 / 弹出层不显示（窄屏下用 JS 将面板设为 `position:fixed` 并按按钮定位）。
- 修复登录页密码输入框比「进入」按钮窄（补齐整行宽度）。
- 设置界面「分区显示名 / 绝对路径」改为两列栅格；设置内操作按钮统一间距；「网页标题」输入整行宽。
- 新增**暗黑模式**（存于浏览器本地，未设置时跟随系统偏好，切换时同步 Vditor 主题与 CSS 变量）。

## 4.0.14（β）

- 前端整体视觉与文案治理（功能与接口不变）：统一为浅色风格并与 Vditor 官方浅色主题对齐；建立全站设计变量（字号 / 色板 / 圆角 / 阴影）并同步给 Vditor 自身变量；统一按钮、输入框、标签、开关控件；清理多套不统一的红 / 灰 / 圆角取值与 JS 硬编码颜色。
- 文案：中文引号统一「」、中文括号统一（）、中英文间补空格；修正与实际按钮名不符的「保存到 NAS」。

## 4.0.13（β）

- 修复 Vditor 顶栏「渲染模式 / 主题 / 导出」等下拉菜单**点击变蓝却不弹出**。根因：v4.0.6 为移动端防换行引入的工具栏横向滚动覆盖被无条件应用到所有宽度，使工具栏成为裁剪容器，而下拉面板以 `absolute` 挂在工具栏按钮内部。现将该组覆盖限定在 `@media (max-width:520px)`，桌面恢复原生样式。

## 4.0.12（β）

- 登录页「忘记密码」改为指引在终端执行 `vditor reset-password`（原需手动删除 `pwhash`）。
- 修复「设置」保存成功提示被设置面板遮罩遮挡（toast 层级提升至所有弹层之上）。
- 安装向导「文档存储文件夹」不再预设路径、默认留空；安装 / 卸载向导说明文案重写。

## 4.0.11（β）

- 修复卸载「删除应用配置」不生效。经实测定位：fnOS 在卸载阶段**不会**把卸载向导字段注入 `uninstall_callback`。改为由 WebUI「设置 → 卸载清理」开关写入 `settings.json`（`clear_on_uninstall`，默认关闭=保留），由回调读文件决定是否清除。原始 Markdown 文档始终保留。

## 4.0.10（β）

- 修复终端命令 `vditor` 找不到：改用 fnOS 官方 **usr-local-linker** 资源把 `app/bin/vditor` 软链到 `/usr/local/bin/vditor`（系统托管），并保留 `/usr/bin`、`/bin` 兜底。
- 修复卸载「删除应用配置」不生效（改用标准向导字段 `data_action`）——**后经实测证伪**，真正的修复在 4.0.11。

## 4.0.9（β）

- 重写 `uninstall_callback`：删除时清除应用配置、历史版本目录与运行时数据，保留原始文档。
- 修复安装后终端 `vditor reset-password` 找不到（软链改为优先写入 `/usr/bin`）。
- 飞牛商店简介补充「功能特色」。

## 4.0.8（β）

- 安装过程自动建立软链，装完即可在终端执行 `vditor reset-password`。
- 修复「文档信息」中删除的二次确认框被信息卡遮挡（确认框恒置顶）。
- **修复 HTTP 登录逻辑**：安全策略强制 HTTPS 时，纯 HTTP 登录直接禁止并提示需改用 HTTPS。

## 4.0.7（β）

- 新增 SSH **一键重置密码**命令（`vditor reset-password`）。
- 修复移动端顶栏「当前文件」被截断（文件名完整显示，顶栏可横向滑动）。
- 新增「备份与恢复说明」；保存按钮改名「保存」且提示显示绝对路径。
- 新增**文档信息**查看与**删除文档（含全部历史版本）**（删除前二次确认）。
- 设置新增**外观设置**：网页标题、网页图标（Favicon）。

## 4.0.6（β）

- 修复安装 / 卸载向导从不触发（向导文件名必须**无扩展名**）。
- 退出登录增加二次确认。
- 修复移动端 Vditor 顶栏换行（横向滑动不换行）。
- 修复侧边栏误显示历史版本文件。
- 新增**配置导入**（此前仅有导出）。

## 4.0.5（β）

- 修复**局域网 HTTP 无法登录**：`Set-Cookie` 强制 `Secure` 导致局域网 HTTP 下浏览器拒存会话。改为仅当确为 HTTPS 或客户端非私有网段时才加 `Secure`，局域网直连自动绕过。
- 修复安装向导未弹 / 无法配置文档文件夹（新增 `doc_dir` 输入项并落盘）。

## 4.0.4（β）

- 收敛与清理：移除已废弃功能的死代码（图床相关路由 / 方法与孤立后端接口）。
- 交付范围确定为 8 项（放弃「粘贴 HTML → Markdown + 外链图片转存图床」）。

## 4.0.3（β）

- **大型功能更新**：WebUI 合并**设置面板**（文件夹设置 + 安全开关 + 修改密码 + 历史版本与自动保存 + 备份导出 + 登录日志）。
- 新增**文件历史版本**（每次保存生成可回溯快照；默认 1 分钟自动保存，可自定义）。
- 新增登录页忘记密码引导、安装向导端口自定义与文件夹引导；顶栏重排。

## 4.0.2（β）

- 二次修复：移除侧栏重复的收起按钮（仅保留顶栏一处）；修复飞牛「访问权限」授权文件夹不显示（增强共享路径解析，并在应用内提供「文件夹设置」直接添加 NAS 文件夹作为分区）。
- 修复 **Markdown 图床外链图片不显示**（CSP 的 `img-src` 过严，放宽为允许外链图片）。

## 4.0.1（β）

- 多分区 + 安全 + 侧栏收起：后端重写为纯标准库版本。
  - **多分区**：飞牛「访问权限」授权目录 / 数据共享目录 / 回退单目录，各分区独立列出文档、互不混淆。
  - **安全**：首次访问设置管理员密码（PBKDF2-HMAC-SHA256）；会话 `HttpOnly + SameSite` Cookie、绑定 IP、空闲 30 分钟 / 绝对 8 小时超时；每 IP 连续 5 次失败锁定 15 分钟；除登录与公开静态资源外所有接口均需登录；含 CSP / `nosniff` / `frame-deny` 响应头。
  - 前端：登录遮罩、多分区侧边栏、侧栏可收起、未选文件保存自动落到首个分区。

## 4.0.0（β，首个 `.fpk`）

- 完成从 0 到 1：把 Vditor 打包为飞牛 fnOS 可用的**非 Docker** 应用（纯静态前端 + Python 标准库后端），支持浏览器自定义端口访问。
- 内置 **NAS 文档管理**：统一在 NAS 目录新建 / 存放 Markdown，WebUI 选择编辑后直接存盘（含子目录、路径穿越防护）。
- 同时产出独立部署包 `vditor-nas-4.0.0.tar.gz` 与官方 `.fpk`（`fnpack` 打包，`.fpk` 实为 tar.gz，内含 `app.tgz`）。

---

## 附：安装包体积一览

| 版本 | 体积（字节） | 说明 |
| --- | --- | --- |
| 4.0.4 | 6,038,538 | |
| 4.0.5 | 12,080,019 | gzip 压缩抖动，内容完整、功能不变 |
| 4.0.6 | 6,040,832 | |
| 4.0.7 | 6,046,700 | |
| 4.0.8 | 6,047,938 | |
| 4.0.9 | 6,049,104 | |
| 4.0.10 | 6,168,471 | |
| 4.0.11 | 6,170,336 | |
| 4.0.12 | 6,169,834 | |
| 4.0.13 | 6,170,569 | |
| 4.0.14 | 6,173,436 | |
| 4.0.15 | 6,176,928 | |
| 4.0.16 | 6,178,047 | |
| 4.0.17 | 6,060,860 | 另有官方 fnpack 构建 6,183,695 |
| 1.0 | 4,547,091 | 包体精简 −27% |
| 1.1 | 4,508,162 | |
| 1.1.1 | 4,509,152 | P0/P1/P2 修复后（含 `vd_util.py` 拆分、静态白名单） |
| 1.1.1 | 4,509,308 | 当前版本（P0+P1 安全/性能加固） |
| 1.1.2 | 4,511,823 | 上传限制放开+可调、网络安全两项默认开启、secure_cookie 关闭放开公网 HTTP |
| 1.1.3 | 4,520,205 | 修复上传未生效（Vditor `accept` 语义）、格式黑名单反转、移动端 API 预留 |
| 1.1.4 | 4,521,423 | 修复黑名单行按钮错位（CSS 特异性）、修复恢复默认后无法保存（连字符扩展名被误判） |
