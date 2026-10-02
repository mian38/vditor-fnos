# 代码评审报告 · Vditor fnOS 应用（com.mian38.vditor）

- **评审版本**：1.1
- **评审范围**：`vditor-fpk/`（`cmd/` 生命周期脚本、`app/server.py` 后端、`app/index.html` 前端、`manifest`/`config`/`wizard`）
- **代码规模**：`server.py` **1880 行**（单文件）、`index.html` **2311 行**（内联 CSS + JS）、`cmd/*` 10 个脚本
- **方法**：通读全部业务代码 + 针对性验证（关键字检索 / 行号定位）。本文只做分析与建议，**未改动任何代码**。

---

## 一、整体架构与模块划分

```
vditor-fpk/
├── manifest            应用元信息（版本、端口、简介、changelog）
├── cmd/                ① fnOS 生命周期脚本（运行在宿主机命名空间）
│   main                 start/stop/status/reset-password
│   install_init/_callback、upgrade_init/_callback
│   uninstall_init/_callback、config_init/_callback、reset-password
├── config/             privilege(run-as:root) + resource(data-share、usr-local-linker)
├── wizard/             install / uninstall（无扩展名 JSON）
└── app/               ② 安装后成为 TRIM_APPDEST，被后端托管
    ├── server.py       单文件后端（配置 / 认证 / 存储 / HTTP 处理器）
    ├── index.html      单页前端（内联 <style> + <script>）
    ├── bin/vditor      终端命令（被软链到 /usr/local/bin）
    ├── ui/             桌面图标与入口配置
    └── vditor/dist/    Vditor 运行时（经精简）
```

**分层**：
- **① 生命周期层**（`cmd/*`）：只做启停、依赖检查、软链、卸载清理；与业务解耦，逻辑简单。它们运行在**宿主机命名空间**，与应用进程的视图不同（曾因此导致"应用内看不到 `/var/apps`"的排查）。
- **② 应用层**：`server.py` 用 Python 标准库实现微型 HTTP 服务（零第三方依赖），静态托管前端 + 提供 JSON API；前端是单页应用，负责全部 UI 与交互。
- **③ 数据层**：无数据库，全部落盘为文件——
  - 配置：`@appconf/<appid>/`（`settings.json` / `pwhash` / `folders.json` / `excluded.json` / `login_log.json` / `port` / `doc_dir` / `favicon.*`）
  - 运行时：`@appdata/<appid>/`（`vditor.log` / `pid`）
  - 文档：各"分区"目录；**每个文档独占一个同名文件夹**，其历史版本在同级 `.vditor_versions/`，上传物与文档同目录

**评价**：分层清晰、部署极简（无依赖、无容器），非常适合 fnOS 场景。主要代价是**两个超大单文件**（后端 1880 行、前端 2311 行），以及**同一份 `server.py` 在 `app/` 与 `vditor-nas/` 各存一份、要求逐字节一致**（靠人工 `cp`，易漂移）。

---

## 二、关键业务逻辑与数据流

### 1) 认证与会话
```
POST /api/login
  → _https_required_error()  ← 非局域网 HTTP 且强制 Secure 时直接 403（并记录 login_blocked_http）
  → is_locked(ip)            ← 每 IP 15 分钟内 5 次失败即锁 15 分钟
  → verify_pwhash(PBKDF2-HMAC-SHA256, 20 万次, compare_digest)
  → start_session() → HttpOnly + SameSite=Lax Cookie（局域网不加 Secure；外网 HTTPS 加）
```
- 会话存**内存字典** `SESSIONS`，绑定客户端 IP，空闲 30 分钟 / 绝对 8 小时过期。
- 除登录、首次设置、公开静态资源外，**所有 API 与 `/uploads/*` 都需登录**（`_require_auth`）。
- 安全响应头（CSP / nosniff / frame-deny）由 `_send` 统一附加。

### 2) 文档读写
```
GET  /api/files  → _api_list_files（对每个分区 os.walk 全树，收集 .md）
GET  /api/file   → _safe_doc → 路径穿越防护 → 读取
                   └─ 命中旧式扁平文档时 _migrate_to_folder_note() 迁移为同名文件夹
POST /api/save   → 旧内容快照进 .vditor_versions/<key>/<ts>.md（有变化才存）
                   → 覆盖写入 → 返回 abspath
```
- 分区来源优先级：`VDITOR_DOC_DIRS` → 飞牛授权目录 / data-share → 应用内手动添加（`folders.json`）→ 回退单目录。
- 路径安全统一走 `safe_join`（`unquote` + `abspath` 前缀校验）。

### 3) 上传与资源引用
```
Vditor upload.extraData = { root, path }（打开文档时同步，写 vditor.vditor.options 的实时对象）
POST /api/upload → 存到「当前文档所在文件夹」→ succMap 返回 <uuid>.<ext>（相对 md 的文件名）
访问：/<uuid>.<ext>  → UPLOAD_NAME_RE 命中 → _find_uploaded() 在各分区文件夹按文件名查找
```
设计意图：让 Markdown 里的引用是**相对路径**，导出/离线可用。

### 4) 备份与恢复
```
GET  /api/backup          → 内存构建 tar.gz（配置目录全部文件 + 各分区 .md + .vditor_versions + 文档文件夹内上传物）
POST /api/backup/restore  → 内存解析上传的 tar.gz（上限 512MB）→ 写回 → 热重载配置与分区
```

---

## 三、核心功能实现方式

| 功能 | 实现要点 |
| --- | --- |
| 多分区文档 | `build_doc_roots()` 汇总多来源 → 去重 → `slugify` 生成 id；`reload_doc_roots()` 热更新 |
| 历史版本 | 以"相对路径去扩展名"为目录键，按毫秒时间戳存 `.md` 快照；保留 `max_versions` 个 |
| 文件版本差异 | `difflib.unified_diff` 与"上一个更早版本"比对，返回 diff 行与增删计数 |
| 上传落位 | 分区内、与文档同目录；相对链接 + `_find_uploaded` 回退解析 |
| 字数统计 | 自研：`vditor.getHTML()`（渲染后 HTML）→ 去标签 → CJK 计 1 字、拉丁字母/数字连续串计 1 词 |
| 移动端下拉面板 | 打开时把面板设 `position:fixed` 并脱离工具栏裁剪（工具栏 `overflow` 保持不动） |
| 大纲侧栏收放 | 窄屏时捕获阶段接管 Vditor 自带的「大纲」按钮（其 `Outline.toggle` 含 520px 宽度门限） |
| 主题 | 浅/暗两套；用户偏好存 localStorage；切换时调 `setTheme` 并同步 Vditor CSS 变量 |
| 卸载清理 | `uninstall_callback` **读 `settings.json` 的 `clear_on_uninstall`** 决定删/留（向导字段在卸载阶段不可用） |

---

## 四、代码质量与可维护性

**优点**
- 零第三方依赖、单文件后端，部署与排障成本极低；注释详尽且说明了"为什么"（含踩坑原因）。
- 关键安全点有明确实现：路径穿越防护、常量时间密码比较、CSP/nosniff、静态文件黑名单、XFF 伪造防护（可选严格模式）。
- 版本/包体/回归测试有脚本化沉淀（`apply_style_v414`、`check_css_clip.py`、6 个回归脚本）。

**问题**
1. **超长单文件**：`server.py` 1880 行把配置、认证、存储、路由、业务混在一起；`index.html` 2311 行内联 CSS+JS。定位成本随功能增长而上升。
2. **同一份后端两份拷贝**：`vditor-fpk/app/server.py` 与 `vditor-nas/server.py` 要求**逐字节一致**（回归测试跑后者），靠人工 `cp` 同步——属于结构性隐患，迟早漂移。
3. **后端缺自动化测试覆盖**：6 个测试脚本全部针对 `vditor-nas`；fpk 专属资源（`/vditor/**`、图标、i18n）只有人工冒烟。
4. 局部重复：`_safe_doc` / `_safe_doc_rel` / `_rel` 职责重叠；`do_GET`/`do_POST` 中 `if not self._require_auth(): return` 重复十余处。
5. 内联 JS 无静态检查（现仅靠 `node --check` 兜底）；常量与字面量混用（`"/uploads/"`、`.vditor_versions` 等）。
6. 副作用偏隐晦：`_api_read_file`（GET）会**移动磁盘文件**；`build_doc_roots` 在导入时 `makedirs`。功能上可接受，但对读代码的人是惊喜。

---

## 五、潜在 bug 与安全隐患

### P0（建议尽快修）
1. **上传无类型白名单 + 同源内联返回 → 存储型 XSS**
   `_handle_upload` 只截取原始扩展名（≤10 字符）就落盘；`guess_mime` 会把 `.html/.svg/.js` 认成对应类型并在 `/uploads/<rid>/<file>`、`/<uuid>.<ext>` **同源返回**。CSP 为 `script-src 'self' 'unsafe-inline'`，被直接打开的恶意 HTML 其内联脚本**会执行**，进而可调用本应用所有 API（携带用户 Cookie）。
   *缓解因素*：需先登录。/ *建议*：扩展名白名单（图片/音频/PDF/压缩包/Office）+ 非白名单一律 `Content-Disposition: attachment`；或对 `/uploads/*` 响应追加 `Content-Security-Policy: sandbox`。

2. **请求体无大小上限（内存 DoS）**
   `int(self.headers.get("Content-Length", 0))` 后直接 `rfile.read(length)`（`server.py` 1102 / 1143 / 1716 / 1785），仅"恢复备份"设了 512MB 上限。任意 API 都可被超大 POST 撑爆内存。
   *建议*：全局 `MAX_BODY`（如 64MB），恢复接口单独放宽；超限返回 413。

3. **`_version_dir` 的键编码存在碰撞**
   键为 `相对目录.replace("/", "__") + "__" + 文件名去扩展名`。`a/b__c.md` 与 `a__b/c.md` 都会得到 `a__b__c` → **两个文档的历史版本互相串用/覆盖**。
   *建议*：改用不可歧义的编码（如 `urlsafe_b64encode(rel).decode()` 或按目录层级 `makedirs`）。

4. **会话与失败计数表无上限、无定期清理**
   `SESSIONS` / `FAIL_LOG` 只在"再次访问同一 token/IP"或登出/改密时清理；长期运行且访客 IP 多时内存持续增长。
   *建议*：加定期 sweep（定时或每次登录时按概率触发）清理过期项。

### P1
5. **`X-Forwarded-Proto: https` 被无条件信任**（`_https_required_error`）：未部署代理时，客户端可自行加上该头，绕过"非局域网 HTTP 不返回应用页面"的页面级拦截。`trust_proxy` 严格模式只约束了 XFF，未约束 Proto。
   *建议*：仅当直连来源为私有/回环（或 `VDITOR_TRUST_PROXY_STRICT` 允许）时才采纳该头。

6. **上传无大小/数量限制**：除备份接口外，单次上传可写满磁盘。建议单文件与单请求配额。

7. **Cookie 未用 `__Host-` 前缀**；CSRF 目前靠"要求 JSON Content-Type + SameSite=Lax"间接防护（对 `/api/upload`、`/api/favicon` 这类 multipart 接口仅靠 Lax）。可加分来源（Origin/Referer）校验。

8. **静态服务采用黑名单**（`is_static_denied` 拦 `*.py/*.env/点文件/敏感 json`）。目前足够，但**将来把新敏感文件放进 `BASE_DIR` 就会被公开**。建议改白名单（放行 `index.html`、`/vditor/**`、`/ui/images/**`）。

### 说明（已妥善处理，无需改动）
- 路径穿越：`safe_join` 已用 `abspath` 前缀校验，跨平台安全。
- 密码存储：PBKDF2-HMAC-SHA256 20 万次 + `compare_digest`，`pwhash` 权限 0600。
- 卸载清理：已证"向导字段在卸载阶段不可用"，现由 `settings.json` 开关决定，逻辑正确。
- 文档迁移：已加"是否已在同名文件夹内"判断，幂等（1.1 修复）。

---

## 六、性能瓶颈

| # | 位置 | 问题 | 影响 |
| --- | --- | --- | --- |
| 1 | 静态资源响应（`_send`，964 行起） | **完全没有缓存头**（无 ETag / Last-Modified / Cache-Control） | 每次打开页面都重新下载 `index.min.js`、`index.css`、icons 等；`/vditor/dist/**` 体积大，首屏明显变慢 |
| 2 | `_api_list_files` | 每次请求对每个分区 `os.walk` **全树** | 大目录/多分区时刷新、保存、新建都卡 |
| 3 | `_find_uploaded` | 每个 `<uuid>.<ext>` 请求**遍历全部分区**查找 | 文档图片多时，每次加载都全盘扫描 |
| 4 | `_api_backup` / `_api_backup_restore` | 在**内存**中构建/解析整个 tar.gz | 文档+上传物多时内存峰值高 |
| 5 | `_send` 读静态文件 | 整个文件读入内存再写（如 `lute.min.js` 3.6MB） | 高并发或大文件时内存与延迟上升 |
| 6 | `updateCounter` | 每次（250ms 防抖）调 `vditor.getHTML()` **整篇渲染** | 大文档连续输入时有可感 CPU 开销 |

---

## 七、可优化 / 重构的地方

**架构层**
- 拆分 `server.py`：`config.py`（配置读写）、`auth.py`（密码/会话/限流）、`store.py`（分区/文档/版本）、`handler.py`（HTTP 路由与业务）。可用包内相对导入，仍保持"零依赖"。
- 前端资源外置：`app.css` / `app.js`（内联目前的好处是少请求 + 便于打包；外置后可用 ESLint/格式化与更细的缓存策略）。**需要权衡**，建议后端缓存头到位后再考虑。
- **消除双份 `server.py`**：改为"单一源 + 构建时复制到 `vditor-nas/`"，或让回归测试直接以 `vditor-fpk/app` 为运行目标。

**健壮性**
- 统一的请求体上限与 413 处理；统一异常兜底（避免未捕获异常导致连接中断）。
- 抽 `@auth_required` 装饰器，消除十余处重复判断。
- 会话/失败计数定期清理；上传配额。

**性能**
- 静态资源加 `ETag`/`Last-Modified`/`Cache-Control`（`/vditor/dist/**` 可 `immutable`），支持 304 —— **投入最小、收益最大**。
- `/api/files` 结果按分区 mtime 缓存；`_find_uploaded` 建一次性 uuid 索引。
- 备份/恢复改流式（写临时文件 + `shutil.copyfileobj`）。
- 字数统计改为"空闲时计算"或按段落增量。

**工程化**
- 增加"包内资源冒烟测试"（检查 `app.tgz` 内静态资源可 200、关键标记在位），纳入常规回归。
- 把 `CHANGELOG.md`、版本号三处（`manifest` + 两个 `APP_VERSION`）纳入一个 `bump_version` 脚本，避免漏改。

---

## 八、改进建议（按优先级）

### P0 — 安全与正确性
1. **上传类型白名单 + 非白名单强制下载（或给 `/uploads/*` 加 CSP sandbox）** —— 消除存储型 XSS。
2. **全局请求体上限**（超限 413）—— 防内存 DoS。
3. **修正 `_version_dir` 键编码** —— 消除版本历史碰撞。
4. **会话 / 失败计数定期清理** —— 防内存缓慢泄漏。

### P1 — 体验与性能
5. **静态资源缓存头（ETag/Last-Modified/304）** —— 首屏与二次加载提速，改动量最小。
6. **`X-Forwarded-Proto` 纳入可信来源判断** —— 补齐 HTTPS 拦截的唯一绕过口。
7. **`/api/files` 与 `_find_uploaded` 加缓存/索引** —— 大目录下的卡顿。
8. **备份/恢复改流式** —— 大库内存峰值。
9. 上传单文件/单请求大小限制。

### P2 — 可维护性
10. 拆分 `server.py` 与前端资源。
11. 消除 `vditor-fpk` ↔ `vditor-nas` 的双份后端。
12. 补齐包内资源冒烟测试与版本号一键同步。
13. 静态服务改白名单策略。

---

## 九、不建议轻易改动的地方（权衡说明）

- **后端保持单文件、零依赖**：这是"fnOS 非 Docker 一键部署"的核心优势；拆包应作为渐进式重构，且需保证 `cmd/main` 的启动方式不变。
- **i18n 必须内联**：线上部署曾出现深层 i18n 静态路径 404 导致编辑器不渲染，内联是根治方案。
- **"每文档一个同名文件夹"数据模型**：已由用户确认，且迁移已幂等；若要调整务必同步改备份、上传、导出与迁移逻辑。
- **内联 CSS/JS 的样式源唯一性约定**：`ui_style_v414.css` 是 `<style>` 的唯一源，`apply_style_v414` 整块替换——绕过它直接改 `index.html` 会被下次同步抹掉。

---

## 十、修复状态（1.1.1，已全量完成）

| # | 建议 | 状态 | 落地 |
| --- | --- | --- | --- |
| 1 | 上传类型白名单 + 强制下载 / CSP 沙箱 | ✅ | `vd_util.upload_headers()`，`/uploads/*` 与 `<uuid>.<ext>` 均生效 |
| 2 | 全局请求体上限（413） | ✅ | `do_POST` 单点：64MB / 256MB / 512MB |
| 3 | 修正 `_version_dir` 键编码 | ✅ | `_version_key()` = 可读前缀 + `sha1[:12]`，`_version_dir()` 懒迁移旧目录 |
| 4 | 会话 / 失败计数定期清理 | ✅ | `_sweep_sessions()`：5 分钟 + 硬上限 5000/10000 |
| 5 | 静态缓存头（ETag/304） | ✅ | `static_headers()` + 流式 `_send_file()` |
| 6 | `X-Forwarded-Proto` 可信判定 | ✅ | `trusted_forwarded_proto()`，仅私网/回环直连才信任 |
| 7 | 文件列表 / 上传查找缓存 | ✅ | `_FILES_CACHE`(2s) + `_UPLOAD_INDEX`(30s)，写操作即时失效 |
| 8 | 备份 / 恢复流式化 | ✅ | 导出 `tempfile` + `_send_file`；恢复支持 raw gzip 请求体流式解包 |
| 9 | 上传单文件 / 单请求大小限制 | ✅ | `MAX_UPLOAD_BYTES` 同 2 |
| 10 | 拆分 `server.py` | ✅（渐进） | 抽出 `vd_util.py`(346 行)；`server.py` 2117→1863 行；可变状态未外迁；顶部 `sys.path` 自举 |
| 11 | 消除 fpk ↔ nas 双份后端 | ✅ | `make_nas.py` 由 `vditor-fpk/app` 派生，`filecmp` 自检 |
| 12 | 包内资源冒烟测试 + 版本号一键同步 | ✅ | `test_smoke_pkg.py`(53 项)、`bump_version.py` |
| 13 | 静态服务改白名单 | ✅ | `is_public_static()`：仅 `/index.html`、`/vditor/`、`/ui/` |

回归 **135/135**（7 个脚本），产物 `releases/com.mian38.vditor_1.1.1.fpk`（4,509,152 字节）。

## 十一、1.1.2 变更（体验与安全策略微调）

| # | 需求 | 状态 | 落地 |
| --- | --- | --- | --- |
| 0 | Cloudflare 穿透下 304 表现 | ✅ 无需改 | 源站 `_send_file()` 的 ETag/Last-Modified 正常；`.js` 显示 200 是 CF 边缘缓存、根 `/` 显示 304 是因为 HTML 回源命中条件请求 |
| 1 | 5 分钟清理 vs 15 分钟锁 | ✅ 不冲突 | `_sweep_sessions()` 仅清 `locked_until<=now 且 first>LOCK_WINDOW`；活跃锁定保留 |
| 2 | 解除上传 10M / 格式限制 + 可调 | ✅ | 前端 `upload` 默认 `accept:'*'`、`max:256MB`；新增 `upload_max_mb`/`upload_accept` 设置；`_handle_upload` 强制校验；`MAX_UPLOAD_BYTES` 提至 512MB |
| 3 | 网络安全两项默认开启 + 关闭二次确认 | ✅ | `DEFAULT_SETTINGS` 默认 `True`（`_bool_default_true`）；前端 `attachSecurityConfirm` 关闭时 `confirm()` 二次确认；文案更新 |
| 4 | secure_cookie 关闭后公网 HTTP 不限制 | ✅ | `_send_cookie()` 仅在 `secure_cookie and not lan` 时加 `Secure`，移除 `proto=='https'` 自动 Secure；开启时仍拦截非局域网 HTTP |
| 5 | 暗黑模式改名 + 说明下置 | ✅ | 标签改「深色模式」，`sub` 说明移至下方 |
| 6 | 网页图标说明更新 | ✅ | sub 改为「此处仅控制前端网页标题与图标……」 |
| 7 | 卸载引导文案重写 | ✅ | `wizard/uninstall` + 设置页说明，强调「以应用内设置为准、Markdown 永不删」 |

定向回归 **28/28**（`test_v112.py`），产物 `releases/com.mian38.vditor_1.1.2.fpk`（4,511,823 字节）。


## 十二、1.1.3 变更（上传修复 + 黑名单反转 + 移动端 API 预留）

| # | 需求 | 状态 | 落地 |
| --- | --- | --- | --- |
| 0 | 排查并修复「上传限制放开 + 可调」未生效 | ✅ 定位到根因并修复 | **根因**：Vditor 的 `accept` 校验为 `accept && accept.split(",").some(t => t[0]==="." ? ext===t : mimeTop===t)`，**无 `*` 分支**——`'*'` 落入 MIME 分支恒假、`''` 走短路亦报错，故 1.1.2 两种写法都会拦掉**全部**上传，服务端校验根本走不到。**修复**：新增 `VDITOR_ACCEPT_ANY`（`split()` 返回 `some()` 恒真对象）短路前端校验，格式判定收归服务端；`upload.max` 仍实时生效 |
| 0b | 配置持久化 / 向后兼容 | ✅ | `load_settings()` 增 `has_deny_key`：**以键是否出现**判断（而非值是否为空），修掉「清空后被默认还原」；`≤1.1.2` 老配置自动补默认黑名单；`upload_accept` 保留但不参与校验，供降级还原 |
| 1 | 上传格式输入控件与同页统一 | ✅ | 根因：`#set-upload-accept` 未纳入 `ui_style_v414.css` 通用输入框选择器组（渲染为浏览器默认外观）。已把 `.set-ext-row input` 并入基础/`:focus`/`::placeholder` 三组；新增 `.set-ext-chip`；`#upload-deny-err` 并入 `#pw-err, #folders-err` 反馈样式；`apply_style_v414` MUST 断言 +3 |
| 2 | 白名单反转为黑名单 | ✅ | `vd_util` 新增 `DEFAULT_UPLOAD_DENY`(67 项)、`normalize_ext_list()`、`is_denied_upload()`；`_handle_upload` 以黑名单为**唯一**依据（删`allow` 分支）；`_apply_settings` 逐项回显非法条目；UI 改可逐条增删的 chip +「添加 / 恢复默认」 |
| 3 | 预留移动端 API | ✅ 规范 only | 新增 `docs/MOBILE_API.md`（15 接口 / 统一响应包 / 9 错误码 / 接入注意 / 6 待确认）；`vd_util.MOBILE_API_PREFIX="/api/m/"` 占位。**无任何路由挂载，调用 404（未实现，符合要求）** |
| 4 | 升版 1.1.3 + 文档 | ✅ | `bump_version.py` 同步 manifest / 两处 `APP_VERSION` / tests；manifest changelog、两份 CHANGELOG、CODE_REVIEW、`docs/MOBILE_API.md` 均已更新 |

**回归**：`test_v113.py` **79/79**（新增：三套服务 + 迁移 + 重启持久化 + 静态/样式断言）、`test_smoke_pkg.py` **53/53**、`test_v112.py` **30/30**（2 项白名单断言已按新语义改写）。
**产物**：`releases/com.mian38.vditor_1.1.3.fpk`（4,520,205 字节）。
**归档**：动手前的 1.1.2 状态已冻结于 `archive/v1.1.2_20261002_1852/`（`diff -r` 校验一致，`.fpk` md5 一致）。

## 十三、1.1.4 变更（黑名单行两处缺陷修复）

| # | 需求 | 状态 | 落地 |
| --- | --- | --- | --- |
| 1 | 「添加」「恢复默认」按钮与输入框对齐 | ✅ 定位到根因并修复 | **根因**：设置区通用规则 `.set-sec button.action { margin: 10px 8px 0 0 }`（特异性 0,2,1）为所有操作按钮加了 10px 上边距；1.1.3 写的 `.set-ext-row button { margin: 0 }`（0,1,1）**特异性不足被压过**，按钮整体下沉。修复为 `.set-sec .set-ext-row button.action { margin: 0; white-space: nowrap; }`（0,3,1）——**靠特异性取胜，与顺序无关**；`apply_style_v414` 加 MUST 断言守护 |
| 2 | 恢复默认后无法保存（`appref-ms` 不合法） | ✅ 根因 + 连带修复 | **根因**：默认清单含连字符项 `appref-ms`，而 `_EXT_TOKEN_RE`（后端）与 `denyTokenValid`（前端）均为 `^[A-Za-z0-9]{1,12}$` → 该项被判非法 → `_apply_settings` 产生 errs → `_api_settings_update` **整次保存被拒**。三处同步放宽为 `^[A-Za-z0-9][A-Za-z0-9-]{0,11}$`，文案改为「需字母开头，仅含字母 / 数字 / 连字符，1–12 位」 |
| 2b | 连字符扩展名落盘后 404（连带发现） | ✅ | `UPLOAD_NAME_RE` 同样不接受连字符，含 `-` 的扩展名上传成功后 `GET /<uuid>.appref-ms` 取不到。同步放宽为 `^[0-9a-f]{32}\.[A-Za-z0-9][A-Za-z0-9-]{0,11}$` |
| 2c | 纵深防御未被削弱 | ✅ | `../bad`、13 位超长、纯 `-`、前导 `-` 仍全部丢弃并在错误提示中列出；`is_denied_upload()` 匹配与强制下载 + CSP sandbox 行为不变 |
| 3 | 升版 1.1.4 + 文档 | ✅ | `bump_version.py` 同步 manifest / 两处 `APP_VERSION` / tests；manifest changelog、两份 CHANGELOG（开发者版含根因、用户版纯用户语言并过术语扫描）、本文件均已更新 |

**回归**：`test_v114.py` **37/37**（新建：按钮对齐 CSS 断言 + 特异性比较、恢复默认后保存成功且 `appref-ms` 落库、连字符扩展名被拦截/移除后可上传且落盘文件 GET 200 + `attachment` + sandbox、非法项仍拒、`vd_util` 纯函数边界、版本号一致性）、`test_v113.py` **79/79**、`test_v112.py` **30/30**、包内冒烟 `test_smoke_pkg.py` **53/53**。
**产物**：`releases/com.mian38.vditor_1.1.4.fpk`（4,521,423 字节；开包核验 manifest `version = 1.1.4`、app 内 399 文件、三处修复标记均在包内）。
**归档**：动手前的 1.1.3 状态已冻结于 `archive/v1.1.3_20261002_1945/`（`diff -r` 一致，`.fpk` md5 `4225211ec6bc28ece174810e4654572f` 一致），其 README 已记录本版修掉的两个问题。

**测试自身的教训**：`test_v114.py` 初版有一条断言写成「override 必须出现在 `.set-sec button.action` 之后」，把**顺序**当成了胜负手，实际 CSS 胜负由**特异性**决定——断言在实现正确时反而误报失败。已改为比较两条选择器的特异性元组，并另加一条「无论顺序都应胜出」的守护断言。

---

# 十四、1.1.4 全量审计与精简报告（同版本内二次修订）

- **审计对象**：`vditor-fpk/app/server.py`（1,910 行）、`vditor-fpk/app/vd_util.py`（417 行）、`vditor-fpk/app/index.html`（2,510 行）、`vditor-fpk/manifest`、`vditor-nas/`（通用版）
- **版本号**：**保持 1.1.4 不变**（本轮为同版本内的代码审计/精简/加固，不改变任何对外功能、接口行为与配置兼容性）
- **方法**：AST 全量扫描 +人工通读 + 实证复现（起真实服务、构造异常请求）+ 产物开包核验
- **结论**：发现并处置 **1 个 High 级缺陷族（4 处）、1 个死函数、13 个未使用 import、3 行空占位注释、6 类重复逻辑**；确认无 Critical 级问题。

## 14.1 审计问题清单（按严重程度）

### 🔴 High（1 项，已全部修复）

| ID | 位置 | 问题 | 影响 | 处置 |
| --- | --- | --- | --- | --- |
| H-1 | `_handle_upload`、`_handle_favicon_upload`、`_api_backup_restore`、`do_POST` | 4 处直接 `int(self.headers.get("Content-Length", 0))`，**无异常保护** | 已登录态下客户端发送非数字 `Content-Length`（如 `abc`）→ `int()` 抛未捕获 `ValueError` → **连接直接断开**（客户端只见空响应），并向 stderr 打完整 traceback。仅 `/api/save` 因外层已有 `try` 而幸免 | 新增 `_content_length()` / `_read_body(handler, limit)` 统一入口，4 处全部改用 |

**实证复现（修复前，已登录态 + `Content-Length: abc`）**：

| 接口 | 修复前| 修复后 |
| --- | --- | --- |
| `/api/save` | 400（`try` 保护） | 400 ✅ |
| `/api/upload` | **`<EMPTY>` 连接被断开 + traceback** | 400/ 413 正常响应 ✅ |
| `/api/favicon` | **`<EMPTY>` 连接被断开 + traceback** | 400 正常响应 ✅ |
| `/api/backup/restore` | **`<EMPTY>` 连接被断开 + traceback** | 400 正常响应 ✅ |

### 🟡 Medium（0 项功能缺陷）

本轮未发现中等严重度的功能性缺陷。Medium 层面只有**代码卫生类问题**（下表），不影响运行行为。

### 🟢 Low / 精简类（18 项，已全部处置）

| ID | 类别 | 位置 | 问题 | 处置 |
| --- | --- | --- | --- | --- |
| L-1 | 死代码 | `server.py` | `_env_bool()` 定义后**全文件0 处引用**（真正生效的是 `_bool_default_true`） | 删除（AST 扫描确认引用数为 0） |
| L-2 | 冗余 import | `server.py` | 13 个名称导入后从未使用：`mimetypes`、`unquote`、`EXTRA_MIME`、`STATIC_DENY_NAMES`、`STATIC_DENY_EXTS`、`CACHE_MAX_AGE`、`UPLOAD_MAX_AGE`、`UPLOAD_INLINE_EXTS`、`UPLOAD_SANDBOX_EXTS`、`_http_date`、`parse_data_share_paths`、`read_share_paths_file` | 清理。**保留 `UPLOAD_NAME_RE`**（初次误删，核查发现 `do_GET` 仍使用 3 次，已补回） |
| L-3 | 空注释 | `server.py` | 3 行空占位分节注释（`# ---- MIME ----` 等），无任何内容 | 删除/合并为 `# ---- 响应安全头 / 缓存策略 ----` |
| L-4 | 重复逻辑 | `server.py` `_send` / `_send_file` | `SEC_HEADERS` 合并 + `_pending_cookie` 处理逻辑重复两遍 | 抽取 `Handler._build_headers(headers=None)` |
| L-5 | 重复逻辑 | `server.py` `is_locked` / `record_failure` | 滑动窗口判定（`first` 超 `LOCK_WINDOW` 则清除）重复 | 抽取 `_fail_entry(ip)` 统一口径 |
| L-6 | 重复逻辑 | `server.py` 12 处 | `try: self._read_json() / except: _send_json(400)` 样板重复 12 次 | 抽取 `Handler._json_body(err="bad json")` |
| L-7 | 重复逻辑 | `server.py` 3 处 | `autosave_interval` / `max_versions` / `upload_max_mb` 的整型校验骨架重复 | 抽取 `Handler._apply_int_setting(...)` |
| L-8 | 重复逻辑 | `vd_util.py` `parse_data_share_paths` / `read_share_paths_file` | JSON 解析分支重复两遍 | 抽取 `_paths_from_json(txt)` |
| L-9 | 口径不一致 | `server.py` `_apply_settings` / `vd_util.normalize_ext_list` | 黑名单切分与校验两处独立实现 | 统一为 `split_ext_tokens(raw)` |
| L-10 | 上限缺失 | `_handle_favicon_upload` | 图标上传沿用 `MAX_BODY_BYTES`（64MB），无贴合上限 | 新增 `FAVICON_MAX_BYTES = 4MB` |

### ⚪ Info（已核查确认无需处置）

| 检查项 | 结论 |
| --- | --- |
| **第三方依赖漏洞** | ✅ **零第三方依赖**，纯 Python 标准库 → 无依赖漏洞面 |
| **危险函数** | ✅ 无 `eval` / `exec` / `pickle` / `subprocess` / `os.system` |
| **敏感信息硬编码** | ✅ 无硬编码密码、密钥、token、内网地址 |
| **路径穿越** | ✅ 统一走 `safe_join()`；备份恢复对 tar 成员做 `..` 检查；测试 C7/C8 穿越读写均被拒 |
| **静态资源越权** | ✅ `PUBLIC_STATIC_EXACT/PREFIX` 白名单 + `is_static_denied()` 兜底；测试 I8 验证 6 条敏感路径全部 404 |
| **XSS** | ✅ `index.html` 18 处 `innerHTML`：服务端数据（登录日志 IP、历史版本 diff、storage_path）全部经 `escapeHtml`；`cls` 来自固定分支；`info[0]` 来自固定白名单 `labels` |
| **调试残留** | ✅ 无 `console.*`、`debugger`、`TODO`/`FIXME` |
| **认证/会话** | ✅ PBKDF2-HMAC-SHA256（200,000 次）+ 16字节随机 salt，`hmac.compare_digest` 常量时间比较；会话 token `secrets.token_urlsafe(32)`；Cookie 含 `HttpOnly; SameSite=Lax; Path=/` |
| **setup 绕过** | ✅ 已设密码后 setup 被拒 403（B8） |
| **失败锁定** | ✅ MAX_FAIL=5 / LOCK_WINDOW=LOCK_DURATION=900 / FAIL_DELAY=0.15；`_sweep_sessions` 只清 `locked_until<=now 且 first>LOCK_WINDOW` 的条目，**活跃锁定完整保留** |
| **包体水分** | ✅ `vditor/` 占 98.5%（360 文件 / 15,385,064 字节），大头为 Vditor 官方运行时（lute 3.74MB / mermaid 3.57MB / graphviz 1.98MB / highlight 1.05MB / echarts 1.03MB）。经核实**全部功能必需**：`viz.js` 是 graphviz wasm 胶水、`third-languages.js` 是代码高亮第三语言包，均由 `index.min.js` 运行时动态加载 → **不可删** |

## 14.2 修改内容清单（含原因与影响范围）

### 新增统一入口（8 个）

| 入口 | 位置 | 改动原因 | 影响范围 |
| --- | --- | --- | --- |
| `_content_length(handler)` | `server.py` | 4 处裸 `int(Content-Length)` 各自解析、防护缺失 | **修复 H-1**。非法值统一归一为 `0`，调用方据此回 4xx。纯新增，不改任何正常路径行为 |
| `_read_body(handler, limit)` | `server.py` | 4 处各自 `rfile.read()`，存在**无上限读入内存**风险 | **修复 H-1 + 纵深防御**。缺失/非法/超限一律返回 `b""`，绝不抛异常、绝不无上限读 |
| `Handler._build_headers(headers)` | `server.py` | `_send`/`_send_file` 两处重复合并 `SEC_HEADERS` + `Set-Cookie` | 行为等价抽取；`Set-Cookie` 语义与清空时机不变 |
| `_fail_entry(ip)` | `server.py` | `is_locked`/`record_failure` 滑动窗口口径重复 | 行为等价抽取，两处共用同一口径 → 顺带消除「两处判定不一致」的隐患 |
| `Handler._json_body(err)` | `server.py` | 12 处 `try/except → 400` 样板 | 行为等价收敛，错误文案逐处保持原值（通过 `err` 参数传入） |
| `Handler._apply_int_setting(...)` | `server.py` | 3 个整型设置字段校验骨架重复 | 行为等价抽取；各字段的范围与错误文案不变 |
| `vd_util.split_ext_tokens(raw)` | `vd_util.py` | 黑名单切分与校验两套实现 | `_SEP_RE = [，,; ]`——**严格不引入换行**，与旧实现对 15 组输入（含 `exe\nexe` 这类边界）**逐项等价** |
| `vd_util._paths_from_json(txt)` | `vd_util.py` | 两处 JSON 解析分支重复 | 行为等价抽取 |

### 删除与清理

| 项 | 改动原因 | 影响范围 |
| --- | --- | --- |
| 删除 `_env_bool()` | AST 扫描确认 0 引用 | 无（死代码） |
| 清理 13 个未使用 import | 冗余 | 无（未使用即无行为） |
| 删除 3 行空占位注释 | 冗余 | 无（注释） |
| `vditor-nas/docs/`（空目录） | 无引用、无消费者 | 无。保留 `vditor-nas/uploads/`（`install.sh` 有 `mkdir -p "$INSTALL_DIR/uploads"`，`config.env` 默认指向该路径） |

### 代码规模变化

| 文件 | 审计前 | 审计后 | 净变化 |
| --- | --- | --- | --- |
| `server.py` | 1,910 行 / 80,285 字节 | **1,906 行 / 80,936 字节** | −4 行 / +651 字节（删死代码与注释，换取8 个统一入口 + 防护） |
| `vd_util.py` | 417 行 / 16,192 字节 | **435 行 / 16,964 字节** | +18 行 / +772 字节（2 个新纯函数 + 文档字符串） |
| `index.html` | 2,510 行 / 127,420 字节 | **2,510 行 / 127,420 字节** | **未改动**（审计未发现需修改的问题） |
| 差异行数 | — | `server.py` 262 行 / `vd_util.py` 60 行（含上下文） | — |

## 14.3 打包体积对比

### fpk（fnOS 官方安装包）

| 阶段 | 字节 | 相对基线 |
| --- | --- | --- |
| 1.1.4 首轮（审计前） | 4,521,423 | 基线 |
| **1.1.4 审计后（当前交付）** | **4,516,769** | **−4,654（−0.10%）** |

**减包来源**：唯一有效来源是 **manifest `changelog` 字段收敛**——从 8,656 字节压到 956 字节（保留 1.1.4 修复条目 + 1.1.3 条目 + 审计条目，删除 1.1.2 及更早历史）。

> 说明：包体 98.5% 是 Vditor 官方运行时（14.1 节已核实全部功能必需），**无可剔除的水分**。代码精简带来的字节变化（+1,423 字节源码）在 gzip 后被压缩抵消，最终净减 4,654 字节。已剔除的还有：`__pycache__`/`*.pyc`（打包前 `rm -rf`）、调试代码（审计确认 0 处）、`vditor-nas/docs/` 空目录。

### nas 通用版

| 产物 | 文件数 | 字节 |
| --- | --- | --- |
| `releases/vditor-nas-1.1.4.tar.gz` | 368 | **4,470,136** |

### 产物核验（开包13 项全过）

| 核验项 | 结果 |
| --- | --- |
| manifest `version` | ✅ `1.1.4` |
| app.tgz 内文件数 | ✅ 397 |
| `server.py` 含 `_content_length` / `_read_body` | ✅ 9 处 |
| `index.html` 含 CSS 特异性修复 | ✅ 1 处 |
| `vd_util.py` 含连字符正则 | ✅ 2 处 |
| `__pycache__` / `*.pyc` 混入 | ✅ 0 |
| 空目录残留 | ✅ 0 |

| 产物 | MD5 |
| --- | --- |
| `releases/com.mian38.vditor_1.1.4.fpk` | `30a2d3fcecb592bc2a3bf587b8fea22d` |
| `releases/vditor-nas-1.1.4.tar.gz` | `4bf5fdc1ac6b3a0ac38cce064df6688c` |

## 14.4 测试结果

### 全量回归 `test_audit114.py`（新建）· 189/189 全部通过

| 段 | 范围 | 项数 | 结果 |
| --- | --- | --- | --- |
| A | CLI / 环境变量 / 配置文件 | 9 | ✅ 9/9 |
| B | 认证与会话（含锁定、改密、登出） | 17 | ✅ 17/17 |
| C | 文档 CRUD（含路径穿越读写） | 10 | ✅ 10/10 |
| D | 上传（含黑名单、连字符、强制下载、体积上限） | 12 | ✅ 12/12 |
| E | 历史版本（列表/diff/恢复/删除/非法 ts） | 6 | ✅ 6/6 |
| F | 设置（保存/校验/导入导出幂等） | 12 | ✅ 12/12 |
| G | 文件夹管理 | 6 | ✅ 6/6 |
| H | 备份与恢复 | 5 | ✅ 5/5 |
| I | 静态资源与安全头（含 6 条敏感路径） | 9 | ✅ 9/9 |
| J | **异常与边界（审计重点）** | 30 | ✅ 30/30 |
| K | 纯函数单元测试 | 47 | ✅ 47/47 |
| L | 代码卫生 | 23 | ✅ 23/23 |

**J 段（审计重点）明细**——12 组非法 `Content-Length`（`abc`/`-1`/空 × upload/favicon/backup-restore/save）全部返回正常状态码、无断连、无 traceback；5 组畸形 JSON 全部 400；超大`Content-Length` → 413；空 body 不崩；未知 GET/POST 路由 → 404；5 个受保护接口未登录 → 401；HEAD 正常；伪造 XFF 无法绕过鉴权。

### 既有回归（审计后复跑，确认零破坏）

| 套件 | 结果 |
| --- | --- |
| `test_v114.py` | ✅ **37/37** |
| `test_v113.py` | ✅ **79/79** |
| `test_v112.py` | ✅ **30/30** |
| `test_smoke_pkg.py`（包内资源冒烟） | ✅ **53/53** |

### 失败项与根因（全部为测试脚本自身问题，非实现缺陷）

迭代过程：179/187 → 182/187 → 183/187 → **189/189**。

| 失败项 | 根因 | 修复 |
| --- | --- | --- |
| J4 超大 `Content-Length` 未 413 | `request()` 助手在 body 非空时**无条件覆写** `Content-Length`，把故意声明的 128MB 覆盖为 2 | 改为 `if "Content-Length" not in h` |
| D11 超限文件未被拒 | 整体请求体超限时服务端按设计在 `do_POST` 顶层就413，断言只看 `errFiles` | 断言放宽为「413 或 errFiles 均可」 |
| K19 `safe_join("/base","/etc/passwd")` 判定为逃逸 | **`safe_join` 语义是「剥前导斜杠后拼到 base 下」**，结果仍在 base 内，非逃逸 | 断言改为「结果必须仍在 base 之内」 |
| L23 目录残留误报 | `app/uploads`、`app/docs` 由 `server.py` 启动时 `os.makedirs` 重建，属运行时目录 | 断言排除这两个运行时空目录 |
| C4/C6/E1–E4 中文 root 404 | **测试脚本 URL 未做百分号编码**（`我的文档` 直接拼进 query）；真实前端用 `encodeURIComponent` | 新增模块级 `enc()`，为所有 URL 的 `root`/`path` 参数补编码 |
| `python -m server` 用例超时 | `subprocess.run(timeout=8)` 对长驻服务必然 `TimeoutExpired` | 改为 `Popen` → 轮询端口 → `terminate()` |
| 中文路径 `UnicodeEncodeError` | 请求行用 latin-1 编码 | 同上 `enc()` 解决 |
| 文档根路径错位一层 | `self.doc` 已是 `<parent>/docs`，环境变量又拼了一次 `doc_sub` → `<parent>/docs/docs` | `"VDITOR_DOC_DIR": self.doc` |

### 测试自身的两条教训

1. **URL 参数必须编码**：真实前端对中文 `root`/`path` 一律走 `encodeURIComponent`，测试脚本直拼会在 404 与「功能失效」之间产生歧义。写HTTP 用例时应默认编码。
2. **不要把实现语义当断言前提**：`safe_join` 的设计是「剥前导斜杠后拼接」而非「拒绝绝对路径」，断言写错会掩盖真实问题。同类还有上一轮的 CSS 顺序 vs 特异性（见十三章）。

## 14.5 遗留风险

| # | 风险 | 等级 | 说明与建议 |
| --- | --- | --- | --- |
| 1 | `X-Forwarded-Proto: https` 被无条件信任 | 低 | 已有已知边界：不经可信代理也可伪造该头绕过 HTTP 登录守卫。彻底修复需引入**可信代理 IP 白名单**，属架构级改动，当前不建议动 |
| 2 | 移动端 API 仅规范、无路由 | 低 | `docs/MOBILE_API.md` 是 15 接口的纯规范，**无任何路由挂载，调用一律 404**。`vd_util.MOBILE_API_PREFIX` 仅占位常量。若日后要实装，勿误以为已可用 |
| 3 | fnOS 卸载向导是静态 JSON | 低 | 应用进程看不到 `/var/apps`（fnOS 文件系统隔离），改向导文案不会实时体现；实际删/留由 `clear_on_uninstall` 决定。**勿再尝试应用侧回写向导** |
| 4 | `_sweep_sessions` 清理窗口 | 低 | 每 5 分钟只清 `locked_until<=now 且 first>LOCK_WINDOW` 的条目，活跃的 15 分钟锁定完整保留，与清理逻辑不冲突 |
| 5 | `set-ext-row` 样式依赖 CSS 特异性 | 低 | 已用0,3,1 特异性压过通用规则并在 `apply_style_v414` 加 MUST 断言守护；但**新增按钮样式时若沿用低特异性写法仍可能重演错位**，改CSS 前务必确认特异性 |
| 6 | `split_ext_tokens` 不接受换行分隔 | 低 | 为严格向后兼容，分隔符集合保持 `[，,; ]`（**不含 `\n`**）。从文件导入黑名单清单时若用换行分行，需先自行转为逗号分隔 |
| 7 | 单文件后端规模 | 信息 | `server.py` 已1,906 行。纯函数已拆至 `vd_util.py`（435 行），但 HTTP 处理器层仍偏大。**下一功能开发前建议先拆 `vd_web.py`**，否则改动风险随规模上升 |
| 8 | 无 CI | 信息 | 全部依赖本地手工跑5 套测试。`test_audit114.py` 已可直接 `python test_audit114.py` 运行（自带 check计数器，不需 pytest），适合接入任一 CI |
