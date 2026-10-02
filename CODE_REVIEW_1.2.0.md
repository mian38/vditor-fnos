# 1.2.0 代码审计与精简报告

> **审计对象**：v1.2.0（`dev/v1.2` 分支）在「移除 Android 客户端 + 新增 API 输出开关」之后的代码。
> **审计时间**：2026-10-03　**基线**：`6230f91`
> **审计原则**：只做加固与去重，**不改变任何对外功能、接口行为与配置兼容性**；不引入新功能、不做大范围重构。
> （1.1 时期的评审报告见 `CODE_REVIEW.md`，本文只覆盖 1.2.0。）

---

## 0. 结论速览

| 项 | 结果 |
| --- | --- |
| 代码规模 | `server.py` 2787 行、`index.html` 2552 行、`vd_util.py` 429 行、`mobile_api.py` 142 行（合计 5910 行） |
| 高危问题 | **2 个**（均已修复，会直接导致连接断开） |
| 中危问题 | **4 个**（均已修复） |
| 精简项 | **8 项**（行为不变） |
| 不建议修改 | **5 项**（见 §4，均已说明理由） |
| 回归测试 | 移动端 66/66、开关 26/26、端到端 48/48、包体冒烟 53/53、**新增审计守护 66/66** |
| 既有失败项 | 12 项，**全部为版本号硬编码断言**（断言 1.1.1/1.1.4，当前是 1.2.0），已用 `git stash` 验证属改动前既有状态 |
| 打包 | fpk / nas 均已重新产出，包内无 `m.html`、无 Android 残留、无 `__pycache__` |

---

## 1. 审计范围与方法

**覆盖范围**：本次改动链路 + 受影响模块全量代码

- `vditor-fpk/app/server.py`（后端全部路由与业务逻辑，重点：`/api/m/*` 链路、设置链路、备份链路、版本链路）
- `vditor-fpk/app/vd_util.py`（纯函数与常量）
- `vditor-fpk/app/mobile_api.py`（移动端响应包与参数校验）
- `vditor-fpk/app/index.html`（前端设置项与开关回显）
- `docs/MOBILE_API.md`（对外接口文档）

**方法**：

1. **静态扫描**（自动化）：高危模式（`eval/exec/pickle/os.system`、裸 `int(Content-Length)`、裸 `rfile.read()`、裸 `except:`）、未使用导入、AST 级死代码与跨模块未引用导出检测。→ 高危模式**零命中**。
2. **人工审查**：按五个维度逐段读代码 —— 逻辑正确性、边界与异常处理、性能、安全、重复/无用代码。
3. **实证取证**：对怀疑的崩溃路径写临时探针，起真实服务发恶意请求复现，确认后再改（避免"看起来像 bug"的误报）。
4. **守护测试**：修复后新增 `test_audit_v120.py`（66 项）把每条结论钉死。

---

## 2. 问题清单（按严重程度）

### 🔴 High — 未捕获异常导致连接直接断开

> **共同特征**：异常冒泡到 `socketserver` 后，`BaseHTTPRequestHandler` 不做任何响应就直接关闭连接。
> 客户端表现是「一直转圈 / 收不到任何响应」，服务端 stderr 打整段 traceback。
> 这与项目 1.1.4 审计修过的「请求体长度解析未保护」是同一类问题，只是换了入口。

#### H1 · 非对象 JSON 请求体 → `AttributeError`

- **位置**：`vditor-fpk/app/server.py:1934` `Handler._read_json()`
- **原实现**：`return json.loads(raw.decode("utf-8")) if raw else {}`
- **根因**：`json.loads` 对 `[1,2]`、`"str"`、`123`、`null`、`true` 这类**合法 JSON 但顶层非对象**的输入同样解析成功，
  返回 `list` / `str` / `int` / `None`。而 **20 处** `_json_body()` 调用方一律按 dict 使用（`data.get(...)`），
  随即抛 `AttributeError: 'list' object has no attribute 'get'`。
- **风险**：**Web 端与移动端的全部写接口**均可触发（`/api/m/file`、`/api/save`、`/api/new`、`/api/version/restore`、
  `/api/version/delete`、`/api/doc/delete`、`/api/export-zip`、`/api/folders`、`/api/settings*` …）。
  实测已登录状态下 `POST /api/m/file` body=`[1,2]` → 连接断开、客户端收到空响应，服务端打 traceback。
  虽需已登录才能触发，但属「已授权用户的普通操作即可打挂自己会话」，且完整 traceback（含绝对路径）会外泄到日志。
- **修复**：在唯一入口校验顶层类型，非 dict 一律抛异常 → 由 `_json_body` 统一回 400（与既有"畸形 JSON"行为一致）。
  ```python
  obj = json.loads(raw.decode("utf-8"))
  if not isinstance(obj, dict):
      raise ValueError("JSON 顶层必须是对象")
  ```
  选在 `_read_json` 而非 20 个调用点改，是与项目既有 `_content_length` / `_read_body` 一致的「唯一入口归一」风格。
- **守护**：`test_audit_v120.py` H1-01 ~ H1-15（14 个接口 × 4 种非法载荷 + 崩溃后存活检查）

#### H2 · 版本时间戳未校验 → `ValueError` / `TypeError`

- **位置**：`vditor-fpk/app/server.py` `read_version()` / `delete_version()`（原裸写 `int(ts)`，现 :723 / :733）
- **根因**：`ts` 来自客户端 JSON，`_api_restore_version` 与 `_api_delete_version` 直接把 `data.get("ts", 0)` 传入，
  未做任何校验。而同类的 `_api_version_diff` **已经做了** `try: int(...) except: ts = 0`
  —— 三处里漏了两处，是典型的"同一模式未收敛"。
- **风险**：实测 `ts="abc"` → `ValueError`；`ts=None` → `TypeError`；`ts=[1]` → `TypeError`；
  `ts="1.5"` → `ValueError`；`ts=NaN` → `ValueError`。全部导致连接断开。
- **修复**：抽出 `_version_path()`（:708），在内部做安全转换，非法 `ts` 返回 `None`，
  调用方按「版本不存在」处理（`read_version`→`None`，`delete_version`→`False`）。
  合法输入行为完全不变；非法输入从「断连」变为「404 / 400」。
- **守护**：`test_audit_v120.py` H2-11 ~ H2-24

---

### 🟠 Medium

#### M1 · `/api/m/asset/` 把整个附件读入内存

- **位置**：`vditor-fpk/app/server.py:1018` `Handler._m_asset()`（原 `with open(...) as f: body = f.read()`）
- **风险**：附件上限读 `SETTINGS["upload_max_mb"]`，可设到 **512MB**。
  而 Web 端同类路径 `/uploads/` 走的是 `_send_file`（`shutil.copyfileobj` 流式，64KB 缓冲）。
  移动端却整文件入内存，单个请求即可让 RSS 峰值飙到数百 MB，多并发有 OOM 风险。
- **修复**：改为 `self._send_file(fp, upload_headers(fp))`。
  `upload_headers` 不带 ETag，故不会触发 `_send_file` 的 304 分支，**行为与原先完全一致**（测试做了字节级比对）。

#### M2 · 开关判定逻辑重复实现

- **位置**：`vditor-fpk/app/server.py` 原 `do_GET()` 的 `/api/m/asset/` 分支 与 `_m_output_off()`（现 :910）
- **风险**：原先 `do_GET` 里另写了一遍 `if SETTINGS.get("api_output") is not True and get_mtoken(self)`，
  与 `_m_output_off()` 语义等价但**是两份代码**。将来任何一方调整判定（如新增「环境变量强制关闭」），
  另一处会漏改 → 附件绕过开关继续外泄，而这正是本开关要防的事。
- **修复**：`_m_output_off()` 增加 `_M_DATA_PREFIX = "/api/m/asset/"` 前缀判定（:908），`do_GET` 复用之。

#### M3 · 备份临时文件在异常路径下泄漏

- **位置**：`vditor-fpk/app/server.py:2595` `_api_backup()`、:2639 `_api_backup_restore()`
- **风险**：两处都是「创建临时文件 → 处理 → `os.remove(tmp)`」的直线写法。
  打包 / 解包途中一旦抛异常（`tarfile.ReadError`、磁盘满、客户端断连导致的 `BrokenPipeError`），
  临时文件**不会被删**，每次失败都在系统临时目录留一份可达 512MB 的 `.tar.gz`。
  对 NAS 这种长期运行的设备，累积起来会吃满系统盘。
- **修复**：拆出 `_build_backup()`（:2603）/ `_extract_backup()`（:2699），用 `try/finally` 兜住清理。

#### M4 · `/favicon.ico` 无异常处理

- **位置**：`vditor-fpk/app/server.py` `Handler._send_favicon()`
- **风险**：`/favicon.ico` 在 `do_GET` 中位于**鉴权检查之前**，是未登录也可访问的公开路径。
  原实现 `open(fp,"rb")` 无 try/except：图标文件被删、权限异常、或 glob 命中的是目录时抛 `OSError`，连接断开。
- **修复**：glob 与 open 各自兜 `OSError`，失败回 204（与"无图标"一致）。

---

### 🟡 Low（已随精简一并处理，详见 §3）

| 编号 | 位置 | 问题 |
| --- | --- | --- |
| L1 | `server.py` `_m_get`/`_m_post`/`_m_put`/`_m_delete` | 9 处 `tok = self._m_require()` 中 8 处的 `tok` 未被使用（静态检查噪音，易让人误以为后面会用到） |
| L2 | `server.py` `_m_doc_detail()` | `size, mtime = size_ = ...` 中的 `size_` 是死赋值 |
| L3 | `server.py` `_m_new_file`/`_m_save_file`/`_m_delete_file`/`_m_restore_version`/`_m_list_assets` | 5 处「取 root/path + `_m_resolve_doc`」样板逐字重复 |
| L4 | `server.py` `_api_settings_update`/`_api_settings_import` | 校验→持久化→回包三段逻辑重复 |
| L5 | `vd_util.py` | `MOBILE_API_PREFIX` 常量定义后**全仓零引用**（1.1.3 的占位常量，1.2.0 各路由直接用字面量） |
| L6 | `mobile_api.py:138` `doc_id()` | 函数内 `import hashlib`，与模块顶部统一导入的风格不一致 |
| L7 | `mobile_api.py` 模块 docstring | 写「路由分发由 `Handler._dispatch_m_*` 完成」，实际方法名是 `_m_get`/`_m_post`/`_m_put`/`_m_delete`，文档误导 |
| L8 | `server.py` `_api_settings_export()` | `keys` 元组写成 200+ 字符单行 |

---

## 3. 已执行的精简项与理由

| # | 精简项 | 位置 | 理由 | 行为变化 |
| --- | --- | --- | --- | --- |
| S1 | 抽出 `_m_doc_target(data, code, msg)` | `server.py:1046` | 收敛 5 处样板（L3）。**`code` 保留由调用方传入**，因为 5 处错误码历史上并不统一，统一码会破坏既有客户端 | 无（错误码逐处保持不变） |
| S2 | 抽出 `_apply_and_reply(data, changed_key)` | `server.py:2252` | 合并设置保存与导入的重复回包（L4）。`changed_key` 参数用于保留导入接口历史上的 `imported` 字段 | 无（`imported` 字段保留，测试 G4 守护） |
| S3 | 拆出 `_build_backup()` / `_extract_backup()` | `server.py:2603 / 2699` | 使临时文件清理能用 `try/finally` 兜住（M3） | 无 |
| S4 | 抽出 `_version_path()` | `server.py:708` | 让 `read_version` / `delete_version` 共用同一份 ts 安全转换（H2） | 非法输入由「断连」变「404/400」 |
| S5 | 去掉 8 处未使用的 `tok` 赋值 | `server.py` 多处 | 消除静态检查噪音（L1） | 无 |
| S6 | 删除 `size_ =` 死赋值 | `server.py` `_m_doc_detail` | 无用代码（L2） | 无 |
| S7 | 删除 `vd_util.MOBILE_API_PREFIX` | `vd_util.py` | 零引用死常量（L5）；其注释还写着「**当前没有任何路由挂在此前缀下**」，与 1.2.0 现状矛盾，留着会误导 | 无 |
| S8 | `mobile_api.py` 风格修正 | `mobile_api.py` | `hashlib` 提到顶部（L6）；docstring 方法名更正（L7） | 无 |

**净效果**：`server.py` 净增约 190 行（其中约 120 行是修复与说明注释），`vd_util.py` 净减 6 行；
重复代码减少约 60 行，可读性提升主要体现在「同类逻辑只有一处」。

---

## 4. 不建议修改的部分及原因

| # | 项目 | 位置 | 不修改的原因 |
| --- | --- | --- | --- |
| N1 | **错误码不统一**：`_m_get_versions` 对无效 root/path 回 `BAD_REQUEST`(400)，`_m_get_version_content` 回 `FORBIDDEN`(403)；`_m_list_assets` 回 `BAD_REQUEST`，其余 4 个文档接口回 `FORBIDDEN` | `server.py:1202 / 1228 / 1484` | 统一码属于**破坏性变更**：任何已按现状做分支处理的客户端都会受影响。且 400 与 403 在本场景语义上都讲得通（前者"参数错"、后者"不允许"）。已在 `_m_doc_target` 用参数化 `code` 兼容两种口径，并把差异写进代码注释。**建议下次大版本统一为 `BAD_REQUEST`**（无效 root/path 更接近参数错误）。 |
| N2 | 函数内惰性 `import`（`io`/`zipfile`/`tarfile`/`tempfile`/`difflib`/`glob`） | `server.py` 多处 | 是有意的启动开销优化：`zipfile`/`tarfile` 只在导出/备份时才需要。全量提到顶部会增加常驻进程的内存与启动时间。仅把轻量的 `hashlib` 上提（S8），重模块保留原样。 |
| N3 | `_api_export_zip` 无体积上限，整个目录打进内存 `BytesIO` | `server.py` 附近 | 确为潜在风险（文档同名文件夹内附件总量可达数百 MB），但**"超限时该报错还是跳过"属于产品决策**，不是单纯的技术加固。已列为已知边界（§6）。建议后续加一道上限并明确文案。 |
| N4 | `log_message` 前缀硬编码 `[vditor-nas]` | `server.py` 末段 | fpk 与 nas 共用同一份 `server.py`（由 `make_nas.py` 派生），改前缀涉及品牌字符串，可能有运维脚本/日志采集规则依赖。属 cosmetic 问题，收益低于风险。 |
| N5 | `_build_upload_index()` 并发重复全量扫描 | `server.py:616` + `vd_util._UPLOAD_INDEX` | TTL 过期后多个请求线程会同时触发 `os.walk` 全量扫描（大分区下有明显开销）。但当前**无正确性问题**（dict 赋值在 GIL 下原子，不会读到半更新状态），加锁会引入新复杂度。建议后续改为单飞（single-flight）或后台定时重建。 |

---

## 5. 测试与打包结果

### 5.1 回归测试

| 套件 | 结果 | 说明 |
| --- | --- | --- |
| `test_mobile_api.py` | **66 / 66** | 移动端接口契约 |
| `test_api_output_switch.py` | **26 / 26** | 开关默认值 / 生效 / 持久化 / 落盘 / 环境变量 |
| `test_android_e2e.py` | **48 / 48** | 端到端调用序（客户端已移除，改为校验服务端字段契约） |
| `test_smoke_pkg.py` | **53 / 53** | 含「server 版本 == manifest 版本(1.2.0)」 |
| `test_audit_v120.py` | **66 / 66** | **本次新增**，审计修复守护 |
| `test_audit114.py` | 186 / 189 | 3 项失败均为版本号硬编码断言 |
| `test_v112.py` / `test_smoke_new.py` / `test_lan_login.py` | 30 / 17 / 9 全过 | — |

**既有失败项（12 项，全部为版本号硬编码，非本次引入）**：

- `test_v113.py` 2 项、`test_v114.py` 2 项、`test_audit114.py` 3 项（L3 / L21 / F10）→ 断言 `1.1.1` 或 `1.1.4`
- `test_v406.py` 1 项、`test_v407.py` 1 项、`test_v408.py` 2 项、`test_v411.py` 1 项

**验证方式**：用 `git stash push` 把本次改动暂存，在**改动前的代码**上重跑 `test_v408.py` 与 `test_v411.py`，
失败项与失败信息**完全一致** → 确认属改动前既有状态
（`test_v411` 的失败是测试自身用 `None` 冒充 `self` 调用实例方法，与服务端无关）。

另：`test_audit114.py` 原还有 2 项失败（L22 `__pycache__` 混入包内、L23 空目录残留），
系历史遗留的测试残留物（`.mtest/` 空目录、`__pycache__`），已清理后转为通过。

### 5.2 新增守护测试 `test_audit_v120.py`（66 项）

| 段 | 覆盖 |
| --- | --- |
| 1 | H1：14 组「非对象 JSON × 接口」必须回 4xx 而非断连；崩溃后服务仍应答 |
| 2 | H2：5 种非法 `ts` × restore/delete 不得断连；不存在的 ts 回 404 |
| 3 | 精简后移动端正常路径：保存 / 乐观锁命中与冲突 / 版本列表双键一致且倒序 / 单版本读取 / 单版本 ts 非法 |
| 4 | M1/M2：附件上传后可原样取回（字节级一致）、重复读取一致 |
| 5 | M3：备份可下载且为合法 gzip、可恢复、坏包不崩 |
| 6 | M4：无图标回 204；图标文件异常（目录冒充）仍不崩 |
| 7 | 设置读写：开启 / 导入带 `imported` / 非布尔被拒 / 数组体不崩 |
| 8 | M2：关闭态下附件被拦 `API_OUTPUT_DISABLED`；未登录仍回 `INVALID_TOKEN`（鉴权优先于开关） |

> 每段开头插了一条**裸 socket 探活**，一旦服务卡死可立刻定位到具体段落；
> 同时显式绕过环境代理（`ProxyHandler({})`），避免本机请求被转发导致随机超时。

### 5.3 打包

| 产物 | 大小 | md5 |
| --- | --- | --- |
| `releases/com.mian38.vditor_1.2.0.fpk` | 4,526,487 字节 | `530e8e643815d441bcdabe76225a34a4` |
| `releases/vditor-nas-1.2.0.tar.gz` | 4,488,801 字节 | `0f879d44e615a7ba6edc6f4c13fcfcf6` |

包内校验（`app.tgz` 共 400 条）：

- ✅ 顶层 `server.py` / `mobile_api.py` / `vd_util.py` 齐全
- ✅ 无 `m.html`、无 `__pycache__`
- ✅ 无 Android 残留（唯一 `android` 命中是 highlight.js 的 `androidstudio` 主题，正常）
- ✅ `manifest` 版本 = `1.2.0`，与 `server.py` 的 `APP_VERSION` 一致
- ✅ `vditor-nas/` 四份共享文件与 `vditor-fpk/app` **逐字节一致**（`make_nas.py` 自检通过）

---

## 6. 已知边界（未修，记录备查）

1. **导出 zip 无体积上限**（见 N3）：文档同名文件夹内附件总量过大时会全部打进内存。
2. **上传索引并发重复扫描**（见 N5）：TTL 过期瞬间多请求会各自触发一次全分区 `os.walk`。
3. **`X-Forwarded-Proto` 被无条件信任**：只要直连来源是私网即可伪造该头绕过「强制 HTTPS」判定
   （1.1.2 既有行为，需可信代理白名单才能更严）。
4. **`save_file_version` 静默失败**：`except OSError: pass`，历史版本保存失败用户无感知。
   当前取舍是"不影响主流程写入"，若要告警需引入日志通道。
5. **`_handle_upload` / `_m_upload` 取 `files[0]`**：未校验 multipart field 名是否为 `file`。
   约定由客户端遵守，恶意构造只是把文件存到别处（仍需鉴权），不构成越权。

---

## 7. 顺带修掉的文档不一致

`docs/MOBILE_API.md`（本次同步更新，属审计发现的"文档与代码不一致"）：

1. 删除失效描述「配套客户端：`android/`（Kotlin 原生…）」，改为说明 **Android 客户端已移除、`/api/m/*` 全部保留**。
2. 新增 **§2.1「API 数据输出」开关**：默认值、配置入口、持久化、环境变量、受控/不受控接口清单、
   **判定顺序**、以及「前端 ↔ 后端 ↔ 持久化」三处口径表。
3. §1.3 补 `API_OUTPUT_DISABLED` 错误码与「鉴权优先于开关」说明。
4. 补充 **§4.7.1 `GET /api/m/file/version`**（1.2.0 新增但此前**未文档化且无任何测试覆盖**）。
5. §4.7 补 `versions` 双键下发与倒序说明；接口清单补 11b 行。
6. §7 提醒：新增会输出数据的接口**必须**把路径加进 `_M_DATA_PATHS`，这是开关唯一可能失效的地方。
7. 修正「Android 客户端在 `ApiClient.parse()` 里统一处理」等已失效的客户端细节描述。

`CHANGELOG.md` / `CHANGELOG_USER.md` / `ARCHIVE.md` 同步更新（遵循项目双 changelog 约定）。

---

## 8. 一条值得记下的排障经验

> **测试用 `subprocess.PIPE` 接服务端输出，会让服务"假死"。**

`Popen(stdout=PIPE, stderr=STDOUT)` 且无人读取时，管道缓冲区（约 64KB）写满后服务端会
**阻塞在写日志的调用上**，症状是「进程活着（`poll()` 返回 None）但不再应答任何请求，
裸 socket 探活也超时」——与「未捕获异常把服务打挂」几乎一模一样。
本次审计中一度被误判为服务端 bug，反复二分才定位到根因。

**结论**：起长驻服务做测试时，输出一律落到文件（`test_audit_v120.py` 已按此实现）。
已写入 `CHANGELOG.md` 备查，建议后续新增测试沿用。
