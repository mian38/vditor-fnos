# Vditor NAS 在线 Markdown 编辑器（飞牛 FnOS 非 Docker 版）

把开源 Markdown 编辑器 [Vditor](https://github.com/Vanessa219/vditor) 打包成一个
**无需 Docker** 的轻量 Web 应用，部署到飞牛 NAS（FnOS）后，浏览器通过**自定义端口**即可访问并使用全部编辑功能。

- 纯静态前端 + 一个 Python 内置标准库写的微型服务器（**零第三方依赖**）
- 支持自定义端口、局域网/公网访问
- 支持图片/文件上传到 NAS 本机
- **多文件夹分区**：对接飞牛「访问权限」或 `VDITOR_DOC_DIRS`，每个文件夹独立分区、互不混淆
- **访问控制**：密码登录（PBKDF2 哈希）+ 会话 Cookie，防暴力破解、防会话劫持，适合经内网穿透在公网使用
- **侧边栏可收起**：释放更多编辑空间
- 跨平台：FnOS、群晖、极空间、任意带 Python3 的 Linux 均可

---

## 一、部署到飞牛 NAS

### 方式 A：SSH 一键安装（推荐）

1. 在飞牛「应用中心 → 终端」或通过 SSH 工具登录 NAS（需 root 权限）。
2. 把本目录（`vditor-nas/`）整个上传到 NAS 任意位置，例如 `/tmp/vditor-nas`。
3. 进入目录并运行安装脚本：

   ```bash
   cd /tmp/vditor-nas
   sudo bash install.sh
   ```

   - 脚本会询问「访问端口」，默认 `3838`，可自定义（如 `8088`）。
   - 脚本自动把文件安装到 `/opt/vditor-nas`，注册 systemd 服务并开机自启。

4. 防火墙放行：飞牛「设置 → 安全/防火墙」中，允许入站 TCP 端口（即你设置的端口，如 3838）。
5. 浏览器访问：`http://<你的NAS的IP>:3838`

### 方式 B：手动运行（无 systemd 也行）

```bash
cd /opt/vditor-nas        # 或任意目录
python3 server.py         # 默认端口见 config.env
```

后台常驻：

```bash
nohup python3 server.py >/var/log/vditor-nas.log 2>&1 &
```

修改端口：编辑 `config.env` 里的 `PORT`，然后重启服务。

---

## 二、自定义端口

两种方式任选其一：

- **安装时指定**：`sudo bash install.sh /opt/vditor-nas 8088`
- **安装后修改**：编辑 `/opt/vditor-nas/config.env` 的 `PORT=xxxx`，然后
  `systemctl restart vditor-nas`（或重启 server.py）。

> 端口范围建议 1024–65535。若使用 1–1023 特权端口，需以 root 运行。

---

## 三、支持的功能

编辑器本身基于 Vditor 4.0.0，开箱即用：

| 功能 | 说明 |
| --- | --- |
| 三种编辑模式 | 即时渲染 / 所见即所得 / 源码 |
| 大纲 | 左侧文档大纲导航 |
| 代码高亮 | 内置 highlight.js，多主题 |
| 数学公式 | KaTeX 渲染 |
| 图表 | 流程图 / 思维导图（markmap）等 |
| 主题 | 明/暗、内容主题、代码主题切换 |
| 导入导出 | 导出 `.md` / `.html`，复制 HTML |
| 自动保存 | 内容存浏览器 localStorage 防丢稿 |
| **文件上传** | 图片/文件上传到 NAS 本机 `/opt/vditor-nas/uploads/` |
| **文档管理** | 左侧按**分区**列出各文件夹的 Markdown 文件，在 NAS 目录中**新建 / 选择 / 编辑 / 保存**，编辑后直接落盘，可经 SMB/FTP 直接访问 |
| **多文件夹分区** | 应用内「文件夹设置」直接指定多个 NAS 文件夹 / 对接飞牛「访问权限」授权目录 / `data-share` 共享目录 / `VDITOR_DOC_DIRS` 显式指定；每文件夹独立分区、清晰隔离 |
| **访问控制** | 首次设置管理员密码后，所有读写接口均需登录；支持防暴力破解锁、防会话劫持 |
| **侧边栏收起** | 编辑区顶部单一按钮可收起/复原侧边栏（收起显示 »、展开显示 «），为编辑区释放空间 |
| **设置面板** | 顶部「设置」按选项卡组织：文件夹、安全、版本与自动保存、上传、维护、外观、关于与帮助 |
| **文件历史版本** | 每次手动/自动保存生成可回溯快照（默认开启，可配置保留数量），支持恢复与删除 |
| **状态与日志 / 改密** | 「维护 → 状态与日志」展示应用状态（浏览器、网络环境、服务器信息）并可查看应用运行日志与登录日志；网页内修改密码并强制重登 |

> 上传与文档管理功能需要本服务器后端（已内置 `/api/upload`、`/api/files`、`/api/file`、`/api/save`、`/api/new`、登录/登出/设置等），
> 因此务必通过本应用访问，而不是直接打开 `index.html` 文件。

### 文档目录（多分区）
应用按**分区**管理 Markdown 文件。推荐用**应用内「文件夹设置」**（编辑区顶部 → 文件夹设置）直接添加 NAS 上的文件夹作为分区，该设置持久化于配置目录 `folders.json`，重启不丢失，且最可靠。

分区来源（合并去重，按绝对路径）：

1. **应用内「文件夹设置」添加的文件夹**（持久化，最推荐）。
2. **`VDITOR_DOC_DIRS`**（显式，任意部署可用）：`名称::路径` 逗号分隔，例如 `工作笔记::/vol1/share/Notes,随笔::/vol1/share/Essays`。
3. **飞牛「访问权限」授权目录**：在飞牛应用设置 → 访问权限 中添加文件夹后，系统可能通过 `TRIM_DATA_SHARE_PATHS`（冒号分隔）或 `share_paths` 文件注入，应用会自动识别并分区（若未出现，请用应用内「文件夹设置」代替）。
4. **`data-share` 共享目录**：安装包已在 `config/resource` 声明 `vditor-docs` 共享目录，作为默认可写分区。
5. **回退单目录**：`VDITOR_DOC_DIR`（默认 `安装目录/docs` 或飞牛运行时 `docs`）。

每个分区在 WebUI 左侧以独立区块展示（📁 分区名 + 该区「+」新建按钮 + 文件列表），分区间文件互不混淆。文件支持子目录。

### WebUI 设置面板（顶部「设置」）

编辑器顶部「设置」按钮打开统一面板，覆盖以下能力（均持久化于配置目录 `settings.json`，重启不丢失）：

- **文件夹设置**：添加 / 删除 NAS 上的文档分区（即原「文件夹设置」，持久化于 `folders.json`）。系统默认分区不在列表内，仅展示可删除的应用内文件夹。
- **安全设置**：
  - 「信任反向代理」：等价于环境变量 `VDITOR_TRUST_PROXY=1`，开启后从 `X-Forwarded-For` 取真实客户端 IP（用于防爆破计数与会话绑定）。
  - 「强制 Cookie Secure」：等价于 `VDITOR_SECURE_COOKIE=1`，全站 HTTPS 时建议开启。
  - **修改登录密码**：校验原密码后更新（PBKDF2 重新哈希并写入 `pwhash`），改密后强制所有会话重新登录。
- **文件版本与自动保存**：
  - 「启用文件历史版本」：每次手动 / 自动保存都会在 `<分区>/.vditor_versions/` 下生成一份旧内容快照，可在「历史版本」中回溯 / 删除。
  - 「每个文件保留的最大版本数」（默认 50）。
  - 「自动保存间隔」（默认 60 秒，最小 10 秒）；编辑区内容在此间隔内若发生改动会自动落盘。
- **维护**：一键**导出备份**（`tar.gz`，含 `folders.json` / `settings.json` / `pwhash` / `login_log.json` 与全部文档）；**状态与日志**（展示应用状态、查看应用运行日志与登录日志）。
- **关于与帮助**：应用简介、开发者与项目地址、开源协议与法律声明；内含**使用指南**与**快捷键**一览。

### 文件历史版本（回溯）

点顶部「历史版本」可查看当前文件的历史快照列表（时间、大小），支持「恢复」（恢复前会先快照当前内容，避免覆盖丢失）与「删除」。历史版本默认开启，可在「设置」中关闭或调整保留数量。

### 忘记密码怎么办

登录页底部已给出引导：在飞牛「终端」删除配置文件 `pwhash` 后，网页会回到首次设置页重设密码；或用环境变量 `VDITOR_PASSWORD` 预置新密码（优先级高于 `pwhash`）。

---

## 访问控制与安全（公网/内网穿透必读）

因应用常经内网穿透在公网暴露，本版本内置访问控制：

- **首次设置**：首次访问网页会要求设置管理员密码（至少 6 位），密码以 **PBKDF2-HMAC-SHA256（20 万次迭代）** 哈希后存入配置目录的 `pwhash` 文件（权限 0600），服务端不保存明文。也可通过 `VDITOR_PASSWORD` / `VDITOR_PWHASH` 预置。
- **会话机制**：登录成功后下发 `HttpOnly` + `SameSite=Lax` 的会话 Cookie（HTTPS 代理下附加 `Secure`），并**绑定客户端真实 IP**、设空闲 30 分钟 / 绝对 8 小时超时。
- **防暴力破解**：每客户端 IP 连续 5 次失败即锁定 15 分钟；失败响应额外延迟 150ms；密码比较使用**常量时间**算法，避免时序侧信道。
- **防未授权访问**：除登录、首次设置与公开静态资源（含 Vditor 前端）外，所有 API 与上传文件均需登录。
- **安全响应头**：内置 `X-Content-Type-Options`、`X-Frame-Options: DENY`、`Content-Security-Policy` 等。CSP 的 `img-src` 已允许外链图片（图床 `https:`/`http:`），因此 Markdown 中直接贴图床链接可正常显示；其余资源仍限制同源以防注入。

> **强烈建议**：① 使用强密码；② 经反向代理/内网穿透时开启 HTTPS 并设置 `VDITOR_TRUST_PROXY=1`，使锁定与 IP 绑定针对真实客户端而非代理 IP；③ 全站 HTTPS 时置 `VDITOR_SECURE_COOKIE=1`。

### 主要环境变量

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `PORT` / `HOST` | 端口 / 监听地址（也可写 `config.env`） | 3838 / 0.0.0.0 |
| `VDITOR_DOC_DIRS` | 多分区：`名称::路径` 逗号分隔 | 空（用访问权限/共享目录） |
| `VDITOR_DOC_DIR` | 单目录回退 | `安装目录/docs` |
| `VDITOR_UPLOAD_DIR` | 上传目录 | `安装目录/uploads` |
| `VDITOR_PASSWORD` | 预置明文密码（不推荐明文） | 空 |
| `VDITOR_PWHASH` | 预置 PBKDF2 哈希（优先于上者） | 空 |
| `VDITOR_CONFIG` | 配置目录（存 `pwhash`） | BASE_DIR / etc |
| `VDITOR_TRUST_PROXY` | 置 1 信任 `X-Forwarded-For`（亦可于 WebUI「设置 → 安全设置」切换，二者等效） | 0 |
| `VDITOR_SECURE_COOKIE` | 置 1 强制 Cookie `Secure`（亦可于 WebUI 切换） | 0 |

---

## 四、目录结构

```
vditor-nas/
├── index.html          # 编辑器页面（入口）
├── server.py           # 微型服务器（静态托管 + 上传接口）
├── config.env          # 端口 / 监听地址配置
├── install.sh          # 安装脚本（systemd）
├── uninstall.sh        # 卸载脚本
├── vditor/             # Vditor 前端资源（含 dist）
├── uploads/            # 运行期上传文件存放处
└── LICENSE             # Vditor MIT 许可证
```

---

## 五、卸载

```bash
sudo bash /opt/vditor-nas/uninstall.sh
```

会停止并移除服务、删除 `/opt/vditor-nas`（含已上传文件，请先备份）。

---

## 六、常见问题

- **打不开页面**：确认端口已放行防火墙；确认服务在运行 `systemctl status vditor-nas`。
- **上传失败**：检查 `uploads/` 目录是否有写权限；查看日志 `/var/log/vditor-nas.log`。
- **想换端口后不生效**：确认改的是 `config.env` 且已 `restart`；环境变量 `VDITOR_PORT` 优先级更高。
- **FnOS 没有 python3**：在飞牛「应用中心」安装「Python3」或终端 `apt install python3`。

---

## 七、许可证

- 编辑器内核：[Vditor](https://github.com/Vanessa219/vditor) © Vanessa219，MIT License
- 本打包脚本与页面：MIT，可自由修改分发
