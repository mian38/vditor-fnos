# 安全策略（Security Policy）

## 支持范围

| 版本 | 支持 |
| --- | --- |
| 1.2.x（当前主线） | ✅ |
| 1.1.5 – 1.1.x | ❌ 仅存档，不再修补 |
| 1.1.4beta（归档） | ❌ 仅存档，不再修补 |
| 4.0.x 及更早| ❌ 已停止维护 |

当前版本号见 [`manifest`](vditor-fpk/manifest) 的 `version=` 字段。

---

## 报告漏洞

**请勿通过公开 GitHub issue 报告安全漏洞。**

本应用处理登录密码（PBKDF2 哈希）与会话数据，公开漏洞细节会让尚未打补丁的
用户直接暴露于风险之中。公开 issue 还会让修复细节提前扩散。

请通过以下方式私下报告：

1. **GitHub 私密漏洞报告**（推荐）—— 仓库页面的 `Security` 选项卡 → `Report a vulnerability`，
   可直接与维护者建立私密对话，无需公开 issue。
2. **邮箱** —— 若上述入口不可用，请通过仓库作者公开渠道获取联系邮箱后直接来信。

### 报告中请包含

- 受影响版本（`manifest` 中的 `version=`）
- 漏洞类型与影响范围
- 复现步骤
- 影响判断（攻击前提条件、需要何种权限）
- 你已知的缓解措施

### 你可以期待什么

| 阶段 | 说明 |
| --- | --- |
| 确认收到 | 3 个工作日内 |
| 初步评估 | 7 个工作日内告知是否受理及严重程度 |
| 修复发布 | 受理后尽快发布修复版本 |
| 公开披露 | 修复发布后公开，**至少留 7 天**给用户升级 |

**请不要在修复发布前公开漏洞细节。**

### 报告范围

**属于本项目范畴**：

- `vditor-fpk/app/server.py`、`vd_util.py` —— 自研后端
- `vditor-fpk/app/index.html`、`ui/` —— 自研前端
- `make_nas.py`、`bump_version.py`、`build_fpk.py` —— 自研构建工具
- NAS 部署脚本 `nas-template/install.sh` / `uninstall.sh`

**不属于本项目范畴**（请向上游报告）：

- 编辑器内核 [Vditor](https://github.com/Vditor/Vditor/issues)（MIT，© Vanessa219 / B3log）
- 第三方渲染组件：KaTeX、highlight.js、Apache ECharts、Mermaid、markmap、
  Graphviz viz.js、abcjs、WaveDrom、flowchart.js、smiles-drawer 等
  完整清单与各自许可见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)

---

## 已实施的安全措施

供评估参考。实现细节以源码为准。

### 认证与会话

| 措施 | 实现 |
| --- | --- |
| 密码存储 | PBKDF2-HMAC-SHA256，20 万次迭代，文件权限 0600，服务端不存明文 |
| 首次设置 | 密码至少 6 位 |
| 会话 Cookie | `HttpOnly` + `SameSite=Lax`，HTTPS 下附加 `Secure` |
| 会话绑定 | 绑定客户端真实 IP |
| 会话超时 | 空闲 30 分钟 / 绝对 8 小时 |
| 常量时间比较 | 密码校验使用常量时间算法，防时序侧信道 |
| 改密失效 | 修改密码后强制所有会话重新登录 |

### 暴力破解防护

| 措施 | 参数 |
| --- | --- |
| 失败锁定 | 同一 IP 连续 5 次失败 → 锁定 15 分钟 |
| 失败延迟 | 每次失败响应额外延迟 150ms |
| 会话清理 | 每 5 分钟清扫过期条目，活跃的 15 分钟锁定完整保留 |

### 请求与响应

| 措施 | 实现 |
| --- | --- |
| 请求体上限 | 统一 `MAX_BODY_BYTES`(64M) / `MAX_UPLOAD_BYTES`(512M) / `BACKUP_MAX_BYTES`(512M) → 413 |
| 请求体解析 | 仅两个受保护入口 `_content_length()` / `_read_body(handler, limit)`，非法长度归一为 0 |
| 安全响应头 | `X-Content-Type-Options`、`X-Frame-Options: DENY`、`Content-Security-Policy` |
| CSP 范围 | `img-src` 允许外链图片（`https:` / `http:`）以支持图床，其余资源限制同源 |
| 上传响应 | 非内联扩展名强制 `Content-Disposition: attachment` + `CSP: sandbox`（防存储型 XSS） |
| 静态白名单 | 仅放行 `index.html` 与 `/vditor/`、`/ui/` 前缀 |

### 网络

| 措施 | 说明 |
| --- | --- |
| `trust_proxy` | 默认**关闭**；开启后采纳 `X-Forwarded-For` 第一段（校验合法 IP） |
| `secure_cookie` | 默认**关闭**；开启后非局域网 HTTP 登录被拒|
| 严格模式 | `VDITOR_TRUST_PROXY_STRICT=1` 严格校验代理来源 |

---

## 部署建议

本应用常经内网穿透暴露到公网，**默认配置不假设你的网络是安全的**。请务必：

1. **启用 HTTPS** —— 公网访问必须走 HTTPS
2. **设置 `VDITOR_TRUST_PROXY=1`** —— 使锁定计数与IP 绑定针对真实客户端，
   而非所有请求都算作代理的同一个 IP。**未开启会导致防爆破形同虚设**
3. **全站 HTTPS 时设置 `VDITOR_SECURE_COOKIE=1`**
4. **使用强密码**
5. **定期导出备份**
6. **保持 NAS 固件与 Python 及时更新**

### 关于 X-Forwarded-Proto 的已知边界

启用 `secure_cookie` 后，HTTP 登录会被拒绝，但当前实现**无条件信任
`X-Forwarded-Proto: https`**。若攻击者能直接构造该请求头且不经过可信代理，
可能绕过 HTTP 限制。更严格的方案需要维护可信代理白名单，当前版本尚未实现。

因此：**不要在无 HTTPS 的公网环境中启用 `secure_cookie` 后就认为万事大吉**，
请确保前置代理会正确覆盖而非透传客户端传入的 `X-Forwarded-*` 头。

---

## 许可

本项目源码采用 [MIT 许可](LICENSE)，Copyright (c) 2026 mian38。
随包分发的第三方组件保留各自许可，清单见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
