# 移动端 API（v1.2.0beta · 已实现 · 归档线）

> ⚠️ **本文档属于 1.2 归档线（标签 `v1.2.0beta`、分支 `archive/v1.2.0beta`）**，
> 主线已回退到 1.1.x。1.2 线暂时归档、不再作为主线维护，代码完整保留、可随时恢复。
>
> **状态：v1.2.0 起 15 个接口全部实装并通过回归测试**（`test_mobile_api.py`，66 项全过）。
> 1.1.3 时期本文只是「预留规范」，当时服务端**没有任何 `/api/m/` 路由**，调用会得到 404；
> 1.2.0 已按本文逐个落地，字段以本文为准。
> 现有 Web 端接口（`/api/login`、`/api/files` 等）保持不变、不受本文影响，
> 且与移动端会话**物理隔离**（独立 `MTOKENS` 字典，不共用 Cookie）。

> ⚠️ **客户端现状（v1.2.0 最终版）**：1.2.0 开发周期内曾附带一个 `android/` 原生客户端，
> **现已彻底移除**（源码、构建脚本、签名凭据、构建环境与 APK 产物均已删除）。
> 本文描述的 `/api/m/*` 服务端能力**全部保留、未做任何删减或降级**，
> 供后续自行开发移动版（原生 App / 小程序 / 第三方客户端）时直接对接。
> 也就是说：**当前版本没有官方移动端 App**，只有这套 API。

---

## 1. 通用约定

| 项目 | 约定 |
| --- | --- |
| 基础路径 | 所有移动端接口统一挂在 `/api/m/` 前缀下，与现有 Web 接口物理隔离，便于并行演进 |
| 传输 | HTTPS（公网访问必须；与现有 `secure_cookie` 安全策略一致） |
| 编码 | 请求与响应均为 `application/json; charset=utf-8`（文件上传除外，用 `multipart/form-data`） |
| 时间 | 一律 ISO 8601 UTC，如 `2026-10-02T10:23:45Z`；**历史版本例外**，用毫秒时间戳（见 §4.7） |
| 字段命名 | `snake_case`（与现有服务端保持一致，便于复用解析逻辑） |

### 1.1 统一响应包

成功：

```json
{ "ok": true, "data": { }, "error": "", "message": "" }
```

失败：

```json
{ "ok": false, "data": null, "error": "INVALID_TOKEN", "message": "登录已失效，请重新登录" }
```

- `ok`：布尔值，客户端据此判断成功与否，**不要**依赖 HTTP 状态码单独判断。
- `error`：机器可读的错误码（见 §5），用于客户端做分支处理。
- `message`：人类可读的中文提示，可直接展示给用户。
- `data` 在失败时为 `null`（不是 `{}`），客户端取值前先判空。

实现位置：`mobile_api.py` 的 `ok()` / `fail()` / `strip_internal()`。
内部约定：以 `_` 开头的键（如 `_http`）为传输用内部字段，输出前由 `strip_internal()` 剥离。

### 1.2 鉴权方式

采用 **Bearer Token**：

```
Authorization: Bearer <token>
```

- 除 `POST /api/m/auth/login` 与 `GET /api/m/health` 外，**所有接口都必须带该头**。
- Token 有效期与 Web 会话一致口径：空闲 30 分钟 / 绝对 8 小时。
- 登录失败次数限制沿用现有策略：同一 IP 连续 5 次失败锁定 15 分钟，失败额外延迟 150ms。
- **Token 不做 IP 绑定**：手机常在蜂窝与 Wi-Fi 间切换，绑定会造成误失效。

Token 存储在服务端的 `MTOKENS` 字典，**与 Web Cookie 会话完全独立**，
便于按客户端维度限流与吊销。硬上限 2000 条，`_sweep_sessions()` 每 5 分钟清理过期项。

### 1.3 通用错误码

| 错误码 | HTTP | 含义 | 客户端建议动作 |
| --- | --- | --- | --- |
| `INVALID_TOKEN` | 401 | token 缺失 / 无效 / 过期 | 清除本地 token，跳转登录 |
| `NEED_SETUP` | 428 | 应用尚未完成首次设置密码 | 引导用户先在 Web 端完成初始设置 |
| `FORBIDDEN` | 403 | 密码错误 / 乐观锁冲突 / 非安全上下文 | 按 message 区分处理 |
| `NOT_FOUND` | 404 | 文档 / 附件不存在 | 刷新列表 |
| `DENIED_EXT` | 400 | 文件扩展名命中上传黑名单 | 提示该类型不允许上传，可在 Web 设置中放开 |
| `TOO_LARGE` | 413 | 文件超过大小上限 | 提示调小文件或调整「上传设置」 |
| `RATE_LIMITED` | 429 | 登录失败次数过多被锁定 | 退避后重试 |
| `BAD_REQUEST` | 400 | 参数缺失 / 类型错误 / 长度超限 | 属端上 bug，需上报 |
| `CONFLICT` | 409 | 同名文档已存在 | 提示换名 |
| `SERVER_ERROR` | 500 | 服务端异常（磁盘满、权限不足等） | 提示重试并上报日志 |
| `API_OUTPUT_DISABLED` | 403 | 「API 数据输出」开关已关闭（见 §2.1） | 提示先在 Web 设置 → 开发者选项开启 |

> 映射表见 `mobile_api.py` 的 `ERROR_HTTP`。未登记的错误码会**降级为 `SERVER_ERROR` + 500**，
> 避免端上遇到未知码时无映射可依。

> ⚠️ **鉴权优先于开关**：未登录（token 缺失/失效）时**一律回 `INVALID_TOKEN`**，
> 即使「API 输出开关」是关闭的。只有「**已登录 + 开关关闭**」才回 `API_OUTPUT_DISABLED`。
> 这样设计是为了避免任何人都能探测出「这台机器有没有开 API 输出」——那属于信息泄露。

---

## 2. 接口清单速查

| # | 方法 | 路径 | 说明 | 鉴权 |
| --- | --- | --- | --- | --- |
| 1 | GET | `/api/m/health` | 健康检查（探活 / 版本） | 否 |
| 2 | POST | `/api/m/auth/login` | 密码登录，下发 token | 否 |
| 3 | POST | `/api/m/auth/logout` | 注销并作废当前 token | 是 |
| 4 | GET | `/api/m/auth/session` | 查询当前会话状态 | 是 |
| 5 | GET | `/api/m/roots` | 列出文档分区（根目录） | 是 |
| 6 | GET | `/api/m/files` | 列出一个分区下的文档列表 | 是 |
| 7 | GET | `/api/m/file` | 获取单个文档详情（内容 + 元信息） | 是 |
| 8 | POST | `/api/m/file` | 新建文档 | 是 |
| 9 | PUT | `/api/m/file` | 保存文档内容（支持乐观锁） | 是 |
| 10 | DELETE | `/api/m/file` | 删除文档（含全部历史版本） | 是 |
| 11 | GET | `/api/m/file/versions` | 列出某文档的历史版本 | 是 |
| 11b | GET | `/api/m/file/version` | 读取某个历史版本的内容（用于对比） | 是 |
| 12 | POST | `/api/m/file/versions/restore` | 回滚到指定历史版本 | 是 |
| 13 | POST | `/api/m/upload` | 上传附件，返回可引用链接 | 是 |
| 14 | GET | `/api/m/settings/upload` | 读取上传限制，供客户端预校验 | 是 |
| 15 | POST | `/api/m/file/assets` | 列出某文档关联的附件 | 是 |
| 附 | GET | `/api/m/asset/<name>` | 读取附件二进制（§4.9 下发 url 的落点） | 是 |

> 全表 16 个接口（15 + 附）；其中 `auth/*` 与 `health` 共 4 个不受「API 数据输出」开关限制，
> 其余 12 个受控，详见 §2.1。

> 新建与保存是**两个独立接口**（8 / 9），不做「有 id 更新、无 id 新建」的合并语义——
> 端上分支更少，且新建可以明确拿到 `CONFLICT` 而不必依赖服务端猜测意图。

### 2.1 「API 数据输出」开关（`api_output`）

v1.2.0 新增一个总开关，控制**是否允许 `/api/m/*` 对外输出实际数据**。

| 项目 | 说明 |
| --- | --- |
| 设置项 | `api_output`（布尔） |
| **默认值** | **关闭（`false`）** |
| 用途定位 | **仅用于开发调试**，日常使用请保持关闭 |
| 配置入口 | Web 端「设置 → 开发者选项 → API 接口对外输出数据」 |
| 持久化 | 写入 `settings.json`，重启后保持 |
| 环境变量 | `VDITOR_API_OUTPUT=1`（或 `true` / `yes`）可在**首次生成配置**时把默认值改为开启 |
| 校验 | 只接受真布尔值；字符串 `"false"` 会被判为无效并拒绝（`_apply_settings` 布尔组） |

**生效范围（受控，开关关闭时返回 `API_OUTPUT_DISABLED` / HTTP 403）：**

```
GET    /api/m/roots                     GET    /api/m/files
GET    /api/m/file                      POST   /api/m/file
PUT    /api/m/file                      DELETE /api/m/file
GET    /api/m/file/versions             GET    /api/m/file/version
POST   /api/m/file/versions/restore     POST   /api/m/file/assets
POST   /api/m/upload                    GET    /api/m/settings/upload
GET    /api/m/asset/<name>
```

**不受控（开关关闭时依然可用）：**

```
GET    /api/m/health                    探活 / 版本号 / setup_completed
POST   /api/m/auth/login                登录（否则调试者连服务是否在线都无法确认）
POST   /api/m/auth/logout               登出
GET    /api/m/auth/session              会话状态
```

**判定顺序（重要）：**

1. 路径不在受控清单 → 放行
2. 开关为 `true` → 放行
3. **当前请求没有有效 token → 放行**（交给鉴权回 `INVALID_TOKEN`）
4. 以上都不满足 → 回 `API_OUTPUT_DISABLED`

第 3 条即「**鉴权优先于开关**」：未登录时一律回 `INVALID_TOKEN` 而不是 `API_OUTPUT_DISABLED`，
避免未授权者据此探测出「这台机器有没有开 API 输出」。

**前端与后端一致性约定**（三处必须同时满足，否则会出现「界面显示开启但接口仍拦截」）：

| 环节 | 写法 | 位置 |
| --- | --- | --- |
| 默认值 | `os.environ.get("VDITOR_API_OUTPUT", "").strip().lower() in ("1","true","yes")` | `server.py` `DEFAULT_SETTINGS` |
| 加载归一化 | `s["api_output"] = (s.get("api_output") is True)` | `server.py` `load_settings()` |
| 应用校验 | 加入 `_apply_settings` 布尔组（`isinstance(v, bool)`） | `server.py` |
| 读取 | `SETTINGS.get("api_output") is True` | `server.py` `_m_output_off()` |
| 前端回显 | `SETTINGS_UI.api_output === true` | `index.html` `loadSettings()` |
| 前端提交 | `checked === true` | `index.html` `saveSettings()` |

> 归一化为 `is True` / `=== true` 而非 `!!` / `===` 布尔转换，是为了防止字符串 `"false"`
> 被当成真值——那会导致「用户明明关了，接口却照常输出数据」。

---

## 3. 鉴权类接口

### 3.1 `GET /api/m/health`

无需鉴权，供客户端启动时探活。响应 `data`：

```json
{
  "status": "ok",
  "app": "com.mian38.vditor",
  "version": "1.2.0",
  "api_version": "m1",
  "time": "2026-10-02T10:23:45Z",
  "setup_completed": true
}
```

`setup_completed=false` 时应引导用户先在浏览器完成首次设置（等价于登录会返回 `NEED_SETUP`）。
客户端可据此区分「服务器没配好」与「地址填错」。

```bash
curl http://192.168.1.10:9000/api/m/health
```

### 3.2 `POST /api/m/auth/login`

**请求：**

```json
{ "password": "用户密码" }
```

**响应 `data`：**

```json
{ "token": "3f9a…（不透明字符串）", "expires_in": 28800, "idle_expires_in": 1800 }
```

**错误：** 密码错误 → `FORBIDDEN`；被锁定 → `RATE_LIMITED`；未完成初始设置 → `NEED_SETUP`；
非安全上下文的 HTTP 登录 → `FORBIDDEN`（message 说明需 HTTPS）。

```bash
curl -X POST http://192.168.1.10:9000/api/m/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"password":"your-password"}'
```

### 3.3 `POST /api/m/auth/logout`

无请求体。作废当前 token。

**语义：幂等。** 无论 token 有效、已失效、还是伪造的，都返回 `ok: true`
（响应 `data` 为 `{"logged_out": true}`）。因为「当前无有效会话」在语义上
就等于「已登出」，不是错误——端上「token 刚过期就点退出」或「重复点退出」
是常态，回 401 只会弹出一个用户看不懂的报错。

> 早期实现曾对无效 token 回 401，与本文档承诺的幂等语义不符，
> 已在 1.2.0 修正（`MOBILE_API.md` 随实现同步更新）。

客户端仍应**无条件清掉本地 token**，不要依赖服务端返回值判断。

```bash
curl -X POST http://192.168.1.10:9000/api/m/auth/logout \
  -H "Authorization: Bearer $TOKEN"
```

### 3.4 `GET /api/m/auth/session`

**响应 `data`：**

```json
{ "authenticated": true, "idle_expires_in": 1500, "abs_expires_in": 21600, "setup_completed": true }
```

客户端据此在 App 回到前台时判断是否需要重新登录。

---

## 4. 文档与附件类接口

### 4.1 `GET /api/m/roots`

**响应 `data`：**

```json
{
  "roots": [
    { "id": "r1", "name": "默认文档", "path": "/vol1/1000/Documents", "hidden": false, "exists": true },
    { "id": "r2", "name": "我的分区", "path": "/vol1/1000/Notes",   "hidden": false, "exists": true }
  ]
}
```

`exists=false` 表示分区目录在磁盘上不存在（常见于外接盘未挂载），端上应灰显并给出说明而非直接报错。

### 4.2 `GET /api/m/files`

列出一个分区下的**单层**条目（文档 + 子目录，不递归）。

**查询参数：**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `root` | 是 | 分区 id |
| `path` | 否 | 子目录相对路径，缺省为分区根目录 |
| `limit` | 否 | 分页条数，默认 200，上限 1000；非法值回落默认 |
| `offset` | 否 | 分页偏移，默认 0 |

**响应 `data`：**

```json
{
  "items": [
    {
      "id": "f1a2b3c4",
      "name": "读书笔记.md",
      "path": "读书笔记/读书笔记.md",
      "root": "r1",
      "size": 20480,
      "updated_at": "2026-10-02T09:10:00Z",
      "is_dir": false,
      "has_versions": true
    },
    {
      "id": "b7d0e512",
      "name": "子目录",
      "path": "子目录",
      "root": "r1",
      "size": 0,
      "updated_at": "2026-10-02T09:00:00Z",
      "is_dir": true,
      "has_versions": false
    }
  ],
  "total": 128,
  "limit": 200,
  "offset": 0
}
```

**排序规则：** 目录在前，同类按 `name` 小写升序。

**两处容易踩空的约定：**

1. **文档的同名文件夹不作为目录条目暴露。**
   文档 `读书笔记/读书笔记.md` 的资源目录 `读书笔记/` 会被跳过（`_in_doc_folder` 判定），
   否则用户点进去只会看到一个同名 `.md`，属于噪音。历史版本目录同理跳过。
2. **无 `word_count` 字段。** Web 端顶栏是按「预览渲染后的可见字数」统计的
   （`index.html` 的 `countReaderWords`），服务端无法复现该口径；
   强行按字符数下发会得到虚高数值，故宁缺勿滥。

### 4.3 `GET /api/m/file` — 文档详情

**查询参数：** `root`（必填）、`path`（必填，相对分区根，指向 `.md` 文件）。

`path` 也接受**只给 stem**（不带 `.md`，如 `读书笔记/读书笔记`），服务端会补 `.md` 再判断。

**响应 `data`：**

```json
{
  "id": "f1a2b3c4",
  "name": "读书笔记.md",
  "path": "读书笔记/读书笔记.md",
  "root": "r1",
  "content": "# 读书笔记\n\n正文…",
  "size": 20480,
  "created_at": "2026-09-30T12:00:00Z",
  "updated_at": "2026-10-02T09:10:00Z",
  "version": 42,
  "assets": [
    { "name": "封面.png", "url": "%E5%B0%81%E9%9D%A2.png", "size": 51200, "ext": "png" }
  ]
}
```

- `version` = 历史版本条数 + 1，即「当前内容算第 N 版」，与 Web 端语义一致。
- `assets[].url` 是**已 URL 编码的相对文件名**（用于 Markdown 引用，不是完整路径）；
  端上要取二进制请拼 `/api/m/asset/<url>`。

### 4.4 `POST /api/m/file` — 新建文档

**请求：**

```json
{ "root": "r1", "path": "读书笔记/读书笔记", "content": "# 标题\n" }
```

文档采用「每文档一个同名文件夹」结构：服务端把 `A/A.md` 与其附件统一放入 `A/` 文件夹。
`path` 传 stem 即可（`A`），服务端经 `_folder_note_path` 规范化；重复调用幂等，不会叠套 `A/A/A.md`。

**响应 `data`：** 同 §4.3。

**错误：** 父路径非法 → `FORBIDDEN`；`root` / `path` 类型或长度非法 → `BAD_REQUEST`；
同名文档已存在 → `CONFLICT`。

```bash
curl -X POST http://192.168.1.10:9000/api/m/file \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"root":"r1","path":"读书笔记/读书笔记","content":"# 标题\n"}'
```

### 4.5 `PUT /api/m/file` — 保存文档

**请求：**

```json
{ "root": "r1", "path": "读书笔记/读书笔记", "content": "# 新内容\n", "if_version": 42 }
```

- 保存时自动生成一次可回溯快照。
- `if_version` 为**乐观锁**（可选）：与服务端当前版本（`version` 字段）不一致则拒绝写入，
  返回 `FORBIDDEN`。**端上务必在加载时记下 `version`，保存时原样回传**，
  这是多端并发编辑下唯一不丢内容的保障。
- 不传 `if_version` 则为「强制覆盖」，仅适合单端独占场景。

**响应 `data`：** 同 §4.3（含更新后的 `version` 与 `updated_at`）。

```bash
curl -X PUT http://192.168.1.10:9000/api/m/file \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"root":"r1","path":"读书笔记/读书笔记","content":"# 新内容\n","if_version":42}'
```

### 4.6 `DELETE /api/m/file` — 删除文档

**请求：** `{"root": "r1", "path": "读书笔记/读书笔记"}`

删除该文档**及其全部历史版本与同名文件夹内的附件**。**不可恢复**，端上必须二次确认。

### 4.7 `GET /api/m/file/versions` — 历史版本列表

**响应 `data`：**

```json
{
  "total": 2,
  "items": [
    { "version": 1757380800000, "created_at": "2026-10-02T09:20:00Z", "size": 20480, "source": "auto", "comment": "" }
  ],
  "versions": [
    { "version": 1757380800000, "created_at": "2026-10-02T09:20:00Z", "size": 20480, "source": "auto", "comment": "" }
  ]
}
```

- 列表按 `version` **倒序**（最新在前），与 Web 端历史面板的阅读顺序一致。
- `items` 与 `versions` **内容完全相同，是同一份数组的两个键**。
  起因：早期端上读 `versions`、服务端只回 `items`，字段名不一致导致移动端列表永远为空。
  现两者同时下发；**新客户端建议读 `versions`**，`items` 仅为兼容保留。
- `total` 为版本条数。

> ⚠️ **`version` 是毫秒时间戳，不是递增序号。** 服务端以保存时刻作为版本标识
> （`v["ts"]`），这样即便跨设备、跨时区也能唯一定位一份快照。
> `created_at` 是同一时刻的 ISO 8601 表示，仅供展示；**回滚时必须回传毫秒时间戳**。
> 端上不要对 `version` 做 `+1` 递增推断——它只用于 `PUT /api/m/file` 的乐观锁。

`source` 固定为 `auto`（每次保存自动生成快照），`comment` 保留字段、当前恒为空串。

### 4.7.1 `GET /api/m/file/version` — 读取某个历史版本内容

供移动端做「历史版本与当前内容对比」（v1.2.0 新增）。

**请求参数：** `root`、`path`（同 §4.7）、`version`（毫秒时间戳，必填，整数）

**响应 `data`：**

```json
{
  "version": 1757380800000,
  "created_at": "2026-10-02T09:20:00Z",
  "size": 20480,
  "content": "# 旧版标题\n\n正文……"
}
```

**错误：** `version` 非整数 → `BAD_REQUEST`；版本不存在 → `NOT_FOUND`；
`root`/`path` 无效或越界 → `FORBIDDEN`（权限校验与 §4.7 一致，均先经 `_m_resolve_doc`）。

```bash
curl -G http://192.168.1.10:9000/api/m/file/version \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "root=r1" --data-urlencode "path=读书笔记/读书笔记" \
  --data-urlencode "version=1757380800000"
```

### 4.8 `POST /api/m/file/versions/restore` — 回滚

**请求：** `{"root": "r1", "path": "…", "version": 1757380800000}`（毫秒时间戳）

回滚会把该版本内容写为当前内容，**并生成一次新的版本快照**，历史链不被破坏。

```bash
curl -X POST http://192.168.1.10:9000/api/m/file/versions/restore \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"root":"r1","path":"读书笔记/读书笔记","version":1757380800000}'
```

### 4.9 `POST /api/m/upload` — 上传附件

`multipart/form-data`，字段如下：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `file` | 是 | 文件二进制（单请求单文件） |
| `root` | 是 | 分区 id |
| `path` | 否 | 所属文档相对路径；缺省则落到全局 uploads 目录 |

**响应 `data`：**

```json
{
  "name": "9f2c8a1b….png",
  "url": "/api/m/asset/9f2c8a1b….png",
  "ext": "png",
  "size": 51200,
  "insert_text": "![](9f2c8a1b….png)"
}
```

**`insert_text` 是给端上最省事的字段**：直接把它插入光标处即得到可用的 Markdown 图片引用
（Web 端 Vditor 用的也是相对文件名，与文档同目录）。

**校验规则（服务端为唯一判定方）：**

1. **大小**：不超过「设置 → 上传设置」中的上限（默认 256MB，可设 1–512MB），
   超出请求体上限直接 `TOO_LARGE` + 断连。
2. **格式**：命中「不允许上传的文件格式」黑名单 → `DENIED_EXT`。
   端上**应先调 §4.10 取回黑名单做预校验以改善体验，但服务端的判定为准**。
3. **Content-Type 必须带 boundary**，否则 `BAD_REQUEST`。
4. 落盘文件名是 `uuid4().hex + "." + ext`，不保留原始文件名（避免路径注入与重名）。
5. 返回的 `url` 可直接 GET 取回二进制（需带 token）；响应头复用 `upload_headers`，
   非内联类型强制 `attachment` + `CSP: sandbox`，防存储型 XSS。

```bash
curl -X POST http://192.168.1.10:9000/api/m/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "root=r1" -F "path=读书笔记/读书笔记" -F "file=@cover.png"
```

### 4.10 `GET /api/m/settings/upload` — 上传限制

供端上上传前预校验与设置页展示。

**响应 `data`：**

```json
{
  "max_mb": 256,
  "min_mb": 1,
  "max_mb_limit": 512,
  "deny_exts": ["exe", "dll", "bat", "js", "html", "…"],
  "default_deny_exts": ["exe", "dll", "bat", "js", "html", "…"]
}
```

- `deny_exts`：当前生效的黑名单（用户在 Web 设置页可增删，**空列表表示不限制**）。
- `default_deny_exts`：内置默认清单，供端上提供「恢复默认」。

> 本接口为**只读**。上传限制目前**仅在 Web 设置页可修改**，移动端不提供修改入口。
> 端上要用黑名单做预校验时，**判「空 = 不限制」**，别把空列表当成「用默认清单」——
> 否则用户清空黑名单后端上仍会拦。

---

## 5. 客户端接入注意事项

1. **不要复用 Web 的 Cookie 登录流程**。移动端走 Bearer Token，避免把密码 Cookie 放进系统 WebView。
2. **401 要统一拦截**。收到 `INVALID_TOKEN` 应清 token 并跳登录页，不要在每个页面各自处理
   （建议在网络层统一拦截，各页面无需重复）。
3. **重试策略要区分故障类型**。网络类瞬时故障（超时、连接重置）可指数退避重试；
   4xx 这类确定性失败重试只会放大无效请求并拖慢反馈。
   **上传不自动重试**（服务端每次都会生成新 uuid，重复提交会产生重复文件）。
4. **`version` 必须参与乐观锁**。加载时存下 `version`，保存时回传；
   收到 `FORBIDDEN` 时**不要覆盖**，应提示用户重新加载对比。
5. **端上不自行统计字数**。服务端不下发 `word_count`（原因见 §4.2），
   端上若要展示应明确标注为「字符数」而非「字数」。
6. **大文档建议本地暂存 + 显式保存**，与 Web 端自动保存策略解耦，避免频繁触网
   （参考做法：停止输入 1.2 秒后静默保存 + 顶栏手动保存兜底）。

---

## 6. 尚未实现（v1.2.0 已知边界）

| # | 议题 | 当前状态 | 后续方案 |
| --- | --- | --- | --- |
| 1 | 上传分片断点续传 | 未做，单请求直传 | 文档场景附件通常较小；超过阈值再引入 |
| 2 | 上传限制端上可改 | 只读 | 确有需求再放开写接口 |
| 3 | 离线编辑队列 | 未做 | 待端上需求明确后再定 |
| 4 | 设备级推送 | 未做 | 可考虑接 fnOS 通知 |
| 5 | 重命名 / 移动文档 | 未开放 | 服务端暂无该能力，端上不给死按钮 |
| 6 | 附件单独删除 | 未开放 | 目前只能随文档一并删除 |

---

## 7. 实现说明（给后续开发者）

- **纯逻辑集中在 `mobile_api.py`**：错误码映射、响应包构造、参数校验、分页解析、时间格式化
  都在这里，`server.py` 只做路由与 I/O。这与项目既有的「纯函数拆 `vd_util.py`」约定一致。
- 新增路由**统一挂在 `/api/m/` 前缀**下，不要与现有 `/api/` 路由混用，便于灰度与回滚。
- `do_GET` / `do_POST` 开头做 `/api/m/` 前缀分流；`do_PUT` / `do_DELETE` 是 1.2.0 新增的
  （Web 端原本没有这两个方法）。
- **「API 数据输出」开关**（§2.1）的判定在 `Handler._m_output_off(path)`，
  受控路径清单是 `Handler._M_DATA_PATHS`（`frozenset`）。
  **新增会输出文档/分区/附件数据的接口时，必须把路径加进该集合**，否则会绕过开关——
  这是本开关唯一可能失效的地方。反之，`health` / `auth/*` 不要加。
- 路径安全**复用现有函数，不要另写一套**：`safe_join`（路径穿越防护）、
  `_safe_doc` / `_m_resolve_doc`（文档定位）、`_doc_asset_dir`（同名文件夹结构）、
  `_folder_note_path`（幂等规范化）、`_version_dir`（版本目录与自动迁移）。
- 上传校验复用 `is_denied_upload`（黑名单）与 `upload_headers`（响应头与沙箱），
  大小上限读 `SETTINGS["upload_max_mb"]` 而非写死常量。
- `_sweep_sessions()` 同时清理 `MTOKENS`，硬上限 2000 条。

> ⚠️ **一个易踩的坑**：`is_denied_upload(filename, deny)` 收的是**完整文件名**
> （内部做 `os.path.splitext` 取扩展名）。传裸扩展名 `"exe"` 会因 `splitext("exe")`
> 得到空扩展名而**漏判放行**，黑名单形同虚设。

- 回归测试：`test_mobile_api.py`（66 项，9 段：A 健康检查与鉴权 / B 登录会话 / C 分区与列表 /
  D 文档 CRUD / E 历史版本 / F 上传限制与附件 / G 异常边界 / H 登出 / I Web 端兼容性）。
  改动移动端接口后必须跑：`python test_mobile_api.py`。
- 静态资源白名单为**白名单放行**机制（仅 `/index.html`、`/vditor/`、`/ui/` 可公开访问），
  新增可公开资源须同步 `PUBLIC_STATIC_EXACT` / `PUBLIC_STATIC_PREFIX`。
