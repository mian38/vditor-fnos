# 移动端 App API 预留接口规范（v1.1.3）

> **状态：仅接口定义预留，尚未实现。** 本文用于给手机端（iOS / Android）先行约定接口形态，
> 待确认后再落地实现。**当前 1.1.3 版本不含任何 `/api/m/` 路由**，调用会得到 404。
> 现有 Web 端接口（`/api/login`、`/api/files` 等）保持不变、不受本文影响。

---

## 1. 通用约定

| 项目 | 约定 |
| --- | --- |
| 基础路径 | 所有移动端接口统一挂在 `/api/m/` 前缀下，与现有 Web 接口物理隔离，便于并行演进 |
| 传输 | HTTPS（公网访问必须；与现有 `secure_cookie` 安全策略一致） |
| 编码 | 请求与响应均为 `application/json; charset=utf-8`（文件上传除外，用 `multipart/form-data`） |
| 时间 | 一律 ISO 8601 UTC，如 `2026-10-02T10:23:45Z` |
| 字段命名 | `snake_case`（与现有服务端保持一致，便于复用解析逻辑） |

### 1.1 统一响应包

成功：

```json
{ "ok": true, "data": { }, "error": "" }
```

失败：

```json
{ "ok": false, "data": null, "error": "INVALID_TOKEN", "message": "登录已失效，请重新登录" }
```

- `ok`：布尔值，客户端据此判断成功与否，**不要**依赖 HTTP 状态码单独判断。
- `error`：机器可读的错误码（见 §5），用于客户端做分支处理。
- `message`：人类可读的中文提示，可直接展示给用户。

### 1.2 鉴权方式

采用 **Bearer Token**：

```
Authorization: Bearer <token>
```

- 除 `POST /api/m/auth/login` 与 `GET /api/m/health` 外，**所有接口都必须带该头**。
- Token 由登录接口下发，有效期与现有 Web 会话一致（空闲 30 分钟 / 绝对 8 小时）。
- 登录失败次数限制沿用现有策略：同一 IP 连续 5 次失败锁定 15 分钟。

> **待确认项**：是否需要为移动端单独签发 token（而非复用 Web 会话 cookie）。
> 建议单独签发，便于服务端按客户端维度限流与吊销。此项在实现前需与项目维护者确认。

### 1.3 通用错误码

| 错误码 | HTTP | 含义 | 客户端建议动作 |
| --- | --- | --- | --- |
| `INVALID_TOKEN` | 401 | token 缺失 / 无效 / 过期 | 清除本地 token，跳转登录 |
| `NEED_SETUP` | 428 | 应用尚未完成首次设置密码 | 引导用户先在 Web 端完成初始设置 |
| `FORBIDDEN` | 403 | 无权限（如非安全上下文下尝试录音类操作） | 提示用户 |
| `NOT_FOUND` | 404 | 文档 / 分区 / 版本不存在 | 刷新列表 |
| `DENIED_EXT` | 400 | 文件扩展名命中上传黑名单 | 提示用户该类型不允许上传，并可在设置中放开 |
| `TOO_LARGE` | 413 | 文件超过大小上限 | 提示用户调小文件或调整「上传设置」 |
| `RATE_LIMITED` | 429 | 请求过于频繁 | 退避后重试 |
| `SERVER_ERROR` | 500 | 服务端异常 | 上报日志并提示重试 |

---

## 2. 接口清单速查

| # | 方法 | 路径 | 说明 | 鉴权 |
| --- | --- | --- | --- | --- |
| 1 | GET | `/api/m/health` | 健康检查（探活 / 版本） | 否 |
| 2 | POST | `/api/m/auth/login` | 账号密码登录，下发 token | 否 |
| 3 | POST | `/api/m/auth/logout` | 注销并作废当前 token | 是 |
| 4 | GET | `/api/m/auth/session` | 查询当前会话状态 | 是 |
| 5 | GET | `/api/m/roots` | 列出文档分区（根目录） | 是 |
| 6 | GET | `/api/m/files` | 列出一个分区下的文档列表 | 是 |
| 7 | GET | `/api/m/file` | 获取单个文档详情（内容 + 元信息） | 是 |
| 8 | POST | `/api/m/file` | 新建文档 | 是 |
| 9 | PUT | `/api/m/file` | 保存文档内容（新建/更新二选一，`id` 为空即新建） | 是 |
| 10 | DELETE | `/api/m/file` | 删除文档（含全部历史版本） | 是 |
| 11 | GET | `/api/m/file/versions` | 列出某文档的历史版本 | 是 |
| 12 | POST | `/api/m/file/versions/restore` | 回滚到指定历史版本 | 是 |
| 13 | POST | `/api/m/upload` | 上传附件（图片 / 音频等），返回可引用链接 | 是 |
| 14 | GET | `/api/m/settings/upload` | 读取上传限制（大小上限 + 格式黑名单），供客户端预校验 | 是 |
| 15 | POST | `/api/m/file/assets` | 列出某文档关联的附件 | 是 |

> 上表中 `PUT /api/m/file` 采用「有 `id` 则更新、无 `id` 则新建」的合并语义，
> 与 8/9 分开的设计二选一即可，**实现时只保留其中一种**（推荐合并式，减少端上分支）。

---

## 3. 鉴权类接口

### 3.1 `GET /api/m/health`

无需鉴权，供客户端启动时探活。

**响应 `data`：**

```json
{
  "status": "ok",
  "app": "com.mian38.vditor",
  "version": "1.1.3",
  "api_version": "m1",
  "time": "2026-10-02T10:23:45Z"
}
```

### 3.2 `POST /api/m/auth/login`

**请求：**

```json
{ "password": "用户密码" }
```

**响应 `data`：**

```json
{
  "token": "3f9a…（不透明字符串）",
  "expires_in": 28800,
  "abs_expires_in": 86400
}
```

**错误：** 密码错误 / 已锁定 → `FORBIDDEN`；未完成初始设置 → `NEED_SETUP`。

### 3.3 `POST /api/m/auth/logout`

无请求体。作废当前 token，重复调用应幂等返回 `ok: true`。

### 3.4 `GET /api/m/auth/session`

**响应 `data`：**

```json
{
  "authenticated": true,
  "idle_expires_in": 1500,
  "abs_expires_in": 21600,
  "setup_completed": true
}
```

客户端据此在 App 回到前台时判断是否需要重新登录。

---

## 4. 文档与附件类接口

### 4.1 `GET /api/m/roots`

列出用户有权限的文档分区。

**响应 `data`：**

```json
{
  "roots": [
    { "id": "r1", "name": "默认文档", "path": "/vol1/1000/Documents", "hidden": false },
    { "id": "r2", "name": "我的分区", "path": "/vol1/1000/Notes",   "hidden": false }
  ]
}
```

### 4.2 `GET /api/m/files`

列出一个分区下的文档（不含子目录递归）。

**查询参数：**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `root` | 是 | 分区 id |
| `path` | 否 | 子目录相对路径，缺省为分区根目录 |
| `limit` | 否 | 分页条数，默认 200，上限 1000 |
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
      "word_count": 5120,
      "updated_at": "2026-10-02T09:10:00Z",
      "is_dir": false,
      "has_versions": true
    }
  ],
  "total": 128,
  "limit": 200,
  "offset": 0
}
```

> `word_count` 口径与 Web 端顶栏一致：按**预览渲染后的可见字数**统计，
> 不含 Markdown 语法，避免端上自行解析得出虚高数值。

### 4.3 `GET /api/m/file` — 文档详情

**查询参数：** `root`（必填）、`path`（必填，相对分区根，指向 `.md` 文件）。

**响应 `data`：**

```json
{
  "id": "f1a2b3c4",
  "name": "读书笔记.md",
  "path": "读书笔记/读书笔记.md",
  "root": "r1",
  "content": "# 读书笔记\n\n正文…",
  "size": 20480,
  "word_count": 5120,
  "created_at": "2026-09-30T12:00:00Z",
  "updated_at": "2026-10-02T09:10:00Z",
  "version": 42,
  "assets": [
    { "name": "封面.png", "url": "/api/m/asset/9f2c…", "size": 51200, "ext": "png" }
  ]
}
```

### 4.4 `POST /api/m/file` — 新建文档

**请求：**

```json
{ "root": "r1", "path": "读书笔记/读书笔记.md", "content": "# 标题\n" }
```

文档采用「每文档一个同名文件夹」结构：服务端会把 `A/A.md` 与其附件统一放入 `A/` 文件夹。

**响应 `data`：** 同 §4.3。

**错误：** 父路径非法 → `FORBIDDEN`；同名文档已存在 → `SERVER_ERROR`（待细化错误码）。

### 4.5 `PUT /api/m/file` — 保存文档

**请求：**

```json
{ "root": "r1", "path": "读书笔记/读书笔记.md", "content": "# 新内容\n", "if_version": 42 }
```

- 开启历史版本时自动生成一次可回溯快照。
- `if_version` 为**乐观锁**（可选）：与服务端当前版本不一致则拒绝写入，
  返回 `FORBIDDEN`，避免多端同时编辑互相覆盖。

**响应 `data`：** 同 §4.3（含更新后的 `version` 与 `updated_at`）。

### 4.6 `DELETE /api/m/file` — 删除文档

**请求：** `{"root": "r1", "path": "读书笔记/读书笔记.md"}`

删除该文档**及其全部历史版本**。建议端上先弹二次确认。

### 4.7 `GET /api/m/file/versions` — 历史版本列表

**响应 `data`：**

```json
{
  "items": [
    {
      "version": 42,
      "created_at": "2026-10-02T09:10:00Z",
      "size": 20480,
      "source": "manual",
      "comment": ""
    }
  ]
}
```

`source` 取值：`manual`（手动保存）/ `auto`（自动保存）。

### 4.8 `POST /api/m/file/versions/restore` — 回滚

**请求：** `{"root": "r1", "path": "…", "version": 40}`

回滚会把该版本内容写为当前内容（**并生成一次新的版本快照**，不破坏历史链）。

### 4.9 `POST /api/m/upload` — 上传附件

`multipart/form-data`，字段如下：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `file` | 是 | 文件二进制（单文件） |
| `root` | 是 | 分区 id |
| `path` | 否 | 所属文档相对路径，用于定位到同名文件夹 |

**响应 `data`：**

```json
{
  "name": "9f2c8a1b….png",
  "url": "/api/m/asset/9f2c8a1b…",
  "ext": "png",
  "size": 51200
}
```

**校验规则（服务端为唯一判定方）：**

1. **大小**：不超过「设置 → 上传设置」中的上限（默认 256MB，可设 1–512MB），超限 → `TOO_LARGE`。
2. **格式**：命中「不允许上传的文件格式」黑名单 → `DENIED_EXT`。
   端上**应先调 §4.10 取回黑名单做预校验以改善体验，但服务端的判定为准**。
3. 返回的 `url` 为可直接插入 Markdown 的引用（相对路径，导出后可离线打开）。

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

- `deny_exts`：当前生效的黑名单（用户在 Web 设置页可增删）。
- `default_deny_exts`：内置默认清单，供端上提供「恢复默认」。

> 本接口为**只读**。1.1.3 的上传限制**仅在 Web 设置页可修改**，
> 移动端暂不提供修改入口（待确认是否放开，见 §6）。

---

## 5. 客户端接入注意事项

1. **不要复用 Web 的 Cookie 登录流程**。移动端走 Bearer Token，避免把密码 Cookie 放进系统 WebView。
2. **401 要统一拦截**。收到 `INVALID_TOKEN` 应清 token 并跳登录页，不要在每个页面各自处理。
3. **上传走分片断点续传**待确认（见 §6），当前设计为单请求直传。
4. **大文档编辑建议本地暂存 + 显式保存**，与 Web 端「自动保存」策略解耦，避免端上频繁触网。
5. **`word_count` 以服务端返回为准**，不要在端上自行统计（含语法会导致虚高）。

---

## 6. 待确认事项（实现前需与维护者对齐）

| # | 议题 | 备选方案 | 建议 |
| --- | --- | --- | --- |
| 1 | Token 签发方式 | 复用 Web 会话 / 单独签发 | 单独签发，便于按客户端限流与吊销 |
| 2 | 上传是否分片 | 单请求直传 / 分片断点续传 | 文档场景附件通常较小，先直传；超过阈值再引入分片 |
| 3 | 上传限制是否允许端上修改 | 只读 / 允许增删黑名单 | 先只读；确有需求再放开写接口 |
| 4 | 是否支持离线编辑队列 | 否 / 是 | 待端上需求明确后再定 |
| 5 | 接口版本化策略 | 路径前缀 / `api_version` 字段 | 采用 `api_version` 字段（已在 §1.1 预留） |
| 6 | 是否需要设备级推送 | 否 / 接入 fnOS 通知 | 待定 |

---

## 7. 实现时的注意事项（给后续开发者）

- 新增路由**统一挂在 `/api/m/` 前缀**下，不要与现有 `/api/` 路由混用，便于灰度与回滚。
- 复用现有工具函数：`safe_join`（路径穿越防护）、`_doc_asset_dir`（同名文件夹结构）、
  `is_denied_upload`（黑名单判定）、`upload_headers`（响应头与沙箱），
  **不要另写一套**上传校验或路径处理逻辑。
- 上传大小上限沿用 `SETTINGS["upload_max_mb"]`，不要写死常量。
- 新接口需补回归测试；现有定向测试见 `test_v113.py`（79 项）。
- 静态资源白名单为**白名单放行**机制（仅 `/index.html`、`/vditor/`、`/ui/` 可公开访问），
  新增需公开访问的路径时必须同步 `vd_util.PUBLIC_STATIC_EXACT` / `PUBLIC_STATIC_PREFIX`，否则 404。