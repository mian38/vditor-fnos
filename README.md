# Vditor for fnOS

把开源 Markdown 编辑器 [Vditor](https://github.com/Vditor/Vditor) 打包成一个**无需 Docker** 的轻量 Web 应用，安装到飞牛 fnOS 后浏览器打开即用。

- 纯静态前端 + 一个用 Python 内置标准库写的微型服务器（**零第三方依赖**）
- 非Docker 部署，由系统进程直接运行，不依赖容器
- 密码登录 + 会话 Cookie，防暴力破解、防会话劫持
- 文档直接落盘到 NAS 目录，可经 SMB / FTP 直接访问

**当前版本：1.2.5** ｜ 许可：[MIT](LICENSE) ｜ 交付形态：fnOS `.fpk` 安装包

> **测试状态：本项目仅在飞牛 fnOS 上构建并实机验证。**
> 后端因零第三方依赖，从代码上可在其他 NAS / Linux 平台运行，但**从未实机验证**，
> 不保证部署可行性、兼容性与稳定性——详见「[免责声明](#免责声明)」。

---

## 目录

- [功能特性](#功能特性)
- [安装方式](#安装方式)
- [环境要求](#环境要求)
- [配置](#配置)
- [从源码构建](#从源码构建)
- [项目结构](#项目结构)
- [开发与测试](#开发与测试)
- [安全](#安全)
- [免责声明](#免责声明)
- [许可](#许可)

---

## 功能特性

编辑器内核基于 Vditor 4.0.0，开箱即用。

| 功能 | 说明 |
| --- | --- |
| 三种编辑模式 | 所见即所得 / 即时渲染 / 源码 |
| 大纲导航 | 左侧文档大纲快速跳转 |
| 代码高亮 | 内置 highlight.js，249 套主题 |
| 数学公式 | KaTeX 渲染 |
| 图表 | 流程图（flowchart.js）、思维导图（markmap）、时序图（WaveDrom）、ECharts 图表、Graphviz 状态图等 |
| 主题切换 | 明/暗模式、内容主题、代码主题 |
| 文档分区 | 把 NAS 上多个文件夹挂载为独立分区，互不混淆 |
| 文件上传 | 图片/文件上传到 NAS 本机，文档内自动插入链接 |
| 历史版本 | 每次保存生成快照，可查看与回滚，误改可救 |
| 访问控制 | 首次设置管理员密码，PBKDF2 哈希存储，全程会话认证 |
| 状态与日志 | 展示应用状态（浏览器、网络环境、服务器信息），可查看应用运行日志与登录日志 |
| 备份导出 | 一键导出「配置 + 文档」完整快照用于容灾 |
| 上传限制 | 黑名单机制，默认拦截可执行文件与脚本，可自定义 |
| 侧边栏收起 | 单按钮收起 / 复原，为编辑区释放空间 |
| 外观自定义 | 网页标题、浏览器图标 |
| 关于与帮助 | 应用简介、开发者、开源协议与法律声明；内含使用指南与快捷键一览 |

> 编辑器为纯前端应用，**必须通过本应用的服务器访问**，直接双击打开 `index.html` 无法使用上传与文档管理（这两项依赖后端 API）。

---

## 安装方式

### 方式 A：fnOS 应用中心（推荐）

1. 从 [Releases](https://github.com/mian38/vditor-nas/releases) 下载 `com.mian38.vditor_<版本>.fpk`
2. 飞牛 fnOS → 应用中心 → 手动安装 → 上传该 `.fpk` 文件
3. 安装完成后浏览器访问 `http://<NAS IP>:3838/`

> 访问端口固定为 **3838**。fnOS 的桌面图标与应用中心入口始终指向安装包内声明的服务端口，
> 不支持在安装向导中自定义——填写自定义端口只会让服务改用该端口监听，图标却仍指向 3838，
> 导致点击图标无法打开。若 3838 已被占用，请先停止占用该端口的服务。
>
> 文档分区在应用内 **右上角「设置 → 文件夹」** 中添加（可添加多个，各分区互相独立）；
> 若要使用 NAS 上已有的目录，需同时在 fnOS 系统「应用中心 → 已安装 → Vditor 编辑器 → 访问权限」中授权。
>
> 本应用为纯 HTTP 服务，不提供 HTTPS，请勿使用 https:// 直接访问；出于安全考虑，暂不支持以 公网IP/域名:3838 在公网直接访问。如需暴露至公网，请使用反向代理 / 内网穿透等方案，并在前置代理处启用 HTTPS。

### 方式 B：其他 NAS / Linux 平台（源码运行 · **未验证**）

> ⚠️ **本项目仅在飞牛 fnOS 上实机验证过，以下方式不保证可用。**
> 后端零第三方依赖，从代码上具备运行条件，但其他平台的目录权限、进程托管、反向代理、
> 文件系统行为等均未验证，风险自负。

本项目的后端（`vditor-fpk/app/server.py`）**零第三方依赖、仅用 Python 标准库**，
且内置 `load_config()`：优先读环境变量 `VDITOR_PORT` / `VDITOR_HOST`，
其次读同目录 `config.env`，最后回退默认 `3838` / `0.0.0.0`。
因此从代码上**无需 fnOS 即可在任意带 Python 3 的 Linux 上启动**：

```bash
git clone https://github.com/mian38/vditor-nas.git
cd vditor-nas/vditor-fpk/app
# 可选：在该目录放一个 config.env（PORT=3838 等），不放在就用默认值
python3 server.py
```

**后台常驻（示例，自行负责）**：可用 systemd 单元或 `nohup` 托管，例如

```bash
nohup python3 server.py >/var/log/vditor.log 2>&1 &
```

> 再次强调：开发者**仅对 fpk（fnOS 安装包）**做过实机功能测试，本节所述的源码部署方式
> **未经任何实机验证**，开发者不对其可行性、稳定性、安全性、兼容性作任何承诺或保证。
> 详见「[免责声明](#免责声明)」。

---

## 环境要求

| 项目 | 要求 |
| --- | --- |
| Python | 3.8 或更高（**仅用标准库，无第三方依赖**） |
| 操作系统 | **飞牛 fnOS**（唯一实机验证平台）；其他 Linux 发行版未验证，见「方式 B」 |
| 浏览器 | 支持 ES6 的现代浏览器 |
| 磁盘 | 应用约 50 MB |

无需 Node.js、无需构建环境、无需 pip install。

---

## 配置

### 环境变量

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `PORT` / `HOST` | 监听端口 / 地址（也可写 `config.env`） | `3838` / `0.0.0.0` |
| `VDITOR_DOC_DIRS` | 多分区：`名称::路径` 逗号分隔 | 空 |
| `VDITOR_DOC_DIR` | 单目录回退 | `安装目录/docs` |
| `VDITOR_UPLOAD_DIR` | 上传目录 | `安装目录/uploads` |
| `VDITOR_CONFIG` | 配置目录（存 `pwhash`） | `BASE_DIR/etc` |
| `VDITOR_PASSWORD` | 预置明文密码（不推荐） | 空 |
| `VDITOR_PWHASH` | 预置 PBKDF2 哈希（优先于上者） | 空 |
| `VDITOR_TRUST_PROXY` | 置 1 信任 `X-Forwarded-For` | 0 |
| `VDITOR_SECURE_COOKIE` | 置 1 强制 Cookie `Secure` | 0 |
| `VDITOR_TRUST_PROXY_STRICT` | 置 1 严格校验代理来源 | 0 |

### 忘记密码

在 NAS 终端删除配置文件 `pwhash` 后，网页会回到首次设置页重设密码：

```bash
# fnOS
sudo /usr/local/bin/vditor reset-password
```

---

## 从源码构建

```bash
git clone https://github.com/mian38/vditor-nas.git
cd vditor-nas
```

### 目录布局约定

本仓库采用「单一源」结构，唯一源即 `vditor-fpk/app/`：

- `vditor-fpk/app/` —— **唯一源**，后端与前端的真实来源，也是通用 Linux 部署的运行代码
- `vditor-fpk/` —— fnOS 打包源目录（`manifest` + `app/`）

改动后端或前端后，只需更新唯一源 `vditor-fpk/app/`。

### 构建 fnOS 安装包

`fnpack.exe` 需从[飞牛官方获取](https://www.fnnas.com)，不随本仓库分发。**交付产物一律由官方 `fnpack.exe` 构建**（仓库中不含自研打包器）。

```bash
rm -rf vditor-fpk/app/__pycache__
fnpack.exe build -d vditor-fpk
```

> 产物 `com.mian38.vditor.fpk` 输出到**当前工作目录**（不是 `-d` 源目录），需手动重命名归档到 `releases/`。
>
> `.fpk` 实为 gzip 压缩的 tar：外层包含 `app.tgz`（即 `app/` 目录内容的 tar.gz）、`LICENSE`、
> `cmd/`、`config/`、`wizard/`、`manifest`、`ICON.PNG`、`ICON_256.PNG`。
>
> 按项目约定，`releases/` 下的构建产物**默认本地保留、不纳入 Git 跟踪**；如需清理请自行确认。

### 升版本号

版本号存于 fpk 两处（`vditor-fpk/manifest` + `vditor-fpk/app/server.py`），
`bump_version.py` 会一次性同步这两处；测试脚本动态读取版本，无硬编码：

```bash
python bump_version.py 1.2.6 --dry-run   # 先预览
python bump_version.py 1.2.6             # 确认后执行
```

---

## 项目结构

```
.
├── vditor-fpk/               # fnOS 打包源
│   ├── manifest              # 应用元信息
│   └── app/                # ← 唯一源
│       ├── server.py            # HTTP 服务、认证、API
│       ├── vd_util.py           # 工具函数与常量
│       ├── index.html           # 单页前端（含内联样式）
│       ├── ui/                  # 前端资源
│       └── vditor/              # Vditor 4.0.0 发行资源
├── docs/                    # 文档
├── test_*.py                # 回归测试（5 个文件，见「开发与测试」）
└── bump_version.py          # 版本号同步（仅 manifest + server.py 两处）
```

---

## 开发与测试

测试脚本自带计数器，**直接运行即可**（不依赖 pytest）：

```bash
python test_version.py      # 版本号一致性
python test_security.py     # 安全/正确性原语
python test_cli.py          # 生命周期脚本语法
python test_pkg.py          # 安装包结构 + 版本
python test_core.py         # 核心功能端到端
```

约定：自 1.1.1 起只对**本轮修改**做定向测试，不再全量回归。

上述测试全部针对 **fpk 交付物**（`vditor-fpk/app/`），在飞牛 fnOS 上验证。本项目**没有**其他平台的自动化测试或实机验证。

贡献流程详见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

---

## 安全

发现安全问题请**不要**提交公开 issue，报告方式见 [`SECURITY.md`](SECURITY.md)。

本项目内置的防护：PBKDF2-HMAC-SHA256（20 万次迭代）密码哈希、HttpOnly + SameSite 会话
Cookie、客户端 IP 绑定、常量时间密码比较、失败锁定（5 次失败锁 15 分钟）、
CSP 与 `X-Frame-Options: DENY` 等安全响应头、非内联扩展名强制下载 + 沙箱。

经内网穿透暴露公网时，**务必**开启 HTTPS 并设置 `VDITOR_TRUST_PROXY=1`。

---

## 免责声明

1. **仅依赖 Python 标准库**：本项目后端仅使用 Python 标准库（`os` / `re` / `json` /
   `hashlib` / `http.server` 等），**不引入任何第三方依赖**，亦不依赖 fnOS 专有 SDK。
   因此无需 `pip install`、无需 Node.js、无需容器，只要有 Python 3.8+ 即可运行。
2. **理论上可二次开发迁移，但从未实机验证**：正因不存在第三方依赖，本项目从代码上
   **具备二次开发并迁移至任何具备 Python 3 环境的 NAS / Linux 平台的条件**——可直接运行
   `vditor-fpk/app/server.py`，或在其基础上自行改造、打包、对接目标平台的进程托管与反向代理。
   但**这仅是理论可行性，不代表已获验证**：本项目唯一实机验证的平台是飞牛 fnOS（fpk 安装包），
   其他 NAS / 发行版 / 容器环境的可行性、兼容性与稳定性均未经验证。
3. **二次开发须遵守开源协议**：你可以按需对本项目进行二次开发、修改与再分发，但**必须严格遵守
   相关开源协议**——本项目源码以 MIT 许可发布（须保留版权声明与许可声明）；随包分发的第三方组件
   （Vditor、ECharts、KaTeX 字体等）保留各自许可，均不在本项目 MIT 许可覆盖范围内，改造与
   分发时须一并保留。
4. **不对二次开发成果作任何保证**：开发者**仅在飞牛 fnOS 上，对基于本仓库代码构建的
   fpk 安装包进行实机功能测试**；对于任何人基于本项目进行的二次开发、衍生版本，
   或在其他 NAS / 发行版 / 容器环境下的部署，开发者**不对稳定性、安全性、兼容性、
   数据完整性等任何方面作任何明示或默示的承诺或保证**。
   二次开发及其部署、运维的风险与责任由使用者自行承担，请在测试环境充分验证后再上生产。

> 简言之：代码开源、可改、可迁移；但「改完能否跑、安不安全、与你平台兼不兼容」，开发者不作背书，由你自己负责。

---

## 许可

本项目源码采用 [MIT 许可](LICENSE)，Copyright (c) 2026 mian38。

随包分发的第三方组件保留各自许可，**不在本项目 MIT 许可覆盖范围内**，
完整清单见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

其中非 MIT 许可的组件需特别注意（各组件目录内附有其许可全文）：

| 组件 | 许可 |
| --- | --- |
| 编辑器内核 Vditor 4.0.0 | MIT，© B3log 开源 |
| Apache ECharts 5.6.0 | Apache-2.0（含 NOTICE 义务，已保留） |
| KaTeX **字体文件** | SIL OFL 1.1（**非 MIT**） |
| Graphviz（Viz.js 内） | EPL-1.0（与 MIT 并存） |
| highlight.js | BSD-3-Clause |
| d3（markmap 内） | ISC |

其余组件（KaTeX 库代码、Mermaid、markmap、abcjs、WaveDrom、flowchart.js、
smiles-drawer、PlantUML Encoder、Lute 等）为 MIT。

更新记录：[`CHANGELOG.md`](CHANGELOG.md)（开发者版）、[`CHANGELOG_USER.md`](CHANGELOG_USER.md)（用户版）。

---

## 开发方式说明

本项目的代码、文档与测试由开发者借助 **AI 编码助手**编写与维护，最终代码经人工审阅、
实机验证与逐版本回归测试后发布。所用 AI 工具不持有本项目代码的著作权，
项目著作权归 [mian38](https://github.com/mian38) 所有，仍以 MIT 许可发布。

欢迎提交 issue 与 PR；因 AI 生成导致的疏漏之处，若你发现问题，欢迎直接指正。
