# Vditor for NAS

把开源 Markdown 编辑器 [Vditor](https://github.com/Vditor/Vditor) 打包成一个**无需 Docker** 的轻量 Web 应用，部署到 NAS 后浏览器打开即用。

- 纯静态前端 + 一个用 Python 内置标准库写的微型服务器（**零第三方依赖**）
- 非Docker 部署，由系统进程直接运行，不依赖容器
- 密码登录 + 会话 Cookie，防暴力破解、防会话劫持
- 文档直接落盘到 NAS 目录，可经 SMB / FTP 直接访问
- 跨平台：飞牛 fnOS、群晖、极空间、任意带 Python 3 的 Linux

**当前版本：1.2.5** ｜ 许可：[MIT](LICENSE)

> 本项目以 **fpk 为唯一发布形态与唯一源**（`vditor-fpk/app/`）。通用 Linux / 任意 NAS 可直接以该目录源码运行（见「安装方式 · 方式 B」与「免责声明」）。

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

### 方式 B：通用 Linux / 任意 NAS（非 fnOS）

本项目的后端（`vditor-fpk/app/server.py`）**零第三方依赖、仅用 Python 标准库**，
且内置 `load_config()`：优先读环境变量 `VDITOR_PORT` / `VDITOR_HOST`，
其次读同目录 `config.env`，最后回退默认 `3838` / `0.0.0.0`。
因此**无需 fnOS，直接在任意带 Python 3 的 Linux / NAS 上运行即可**。

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

> ⚠️ 通用 Linux / 非 fnOS 平台的部署**不在本项目的发布与实机测试范围内**，
> 详见下方「[免责声明](#免责声明)」。

---

## 环境要求

| 项目 | 要求 |
| --- | --- |
| Python | 3.8 或更高（**仅用标准库，无第三方依赖**） |
| 操作系统 | Linux（fnOS / 任意发行版） |
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

`fnpack.exe` 需从[飞牛官方获取](https://www.fnnas.com)，不随本仓库分发。

```bash
rm -rf vditor-fpk/app/__pycache__
fnpack.exe build -d vditor-fpk
```

### 升版本号

版本号存于 fpk 两处（`manifest` + `vditor-fpk/app/server.py`）+ 测试脚本，
`bump_version.py` 会一次性同步 fpk 相关位置：

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
├── test_*.py                # 回归测试
├── bump_version.py          # 版本号同步（仅 fpk）
└── build_fpk.py             # fpk 构建（如有）
```

---

## 开发与测试

测试脚本自带计数器，**直接运行即可**（不依赖 pytest）：

```bash
python test_audit114.py     # 1.1.4 全量回归
python test_v114.py         # 1.1.4 定向测试
python test_smoke_pkg.py    # 包内资源冒烟
```

约定：自 1.1.1 起只对**本轮修改**做定向测试，不再全量回归。

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
2. **理论可二次开发迁移**：正因不存在第三方依赖，本项目在理论上**支持二次开发并迁移至任何
   具备 Python 3 环境的 NAS / Linux 平台**——直接运行 `vditor-fpk/app/server.py`，或在其基础上
   自行改造、打包、对接目标平台的进程托管与反向代理。
3. **二次开发须遵守开源协议**：你可以按需对本项目进行二次开发、修改与再分发，但**必须严格遵守
   相关开源协议**——本项目源码以 MIT 许可发布（须保留版权声明与许可声明）；随包分发的第三方组件
   （Vditor、ECharts、KaTeX 字体等）保留各自许可，均不在本项目 MIT 许可覆盖范围内，改造与
   分发时须一并保留。
4. **不对二次开发成果作任何保证**：开发者**仅对基于本仓库代码构建的 fpk（fnOS 安装包）进行实机
   功能测试**；对于任何人基于本项目进行的二次开发、衍生版本，或在其他 NAS / 发行版 / 容器环境下的
   部署，开发者**不对稳定性、安全性、兼容性、数据完整性等任何方面作任何明示或默示的承诺或保证**。
   二次开发及其部署、运维的风险与责任由使用者自行承担，请在测试环境充分验证后再上生产。

> 简言之：代码开源、可改、可迁移；但「改完能否跑、安不安全、与你平台兼不兼容」，开发者不作背书，由你自己负责。

---

## 许可

本项目源码采用 [MIT 许可](LICENSE)，Copyright (c) 2026 mian38。

随包分发的第三方组件保留各自许可，**不在本项目 MIT 许可覆盖范围内**，
完整清单见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

其中需特别注意：

- 编辑器内核 Vditor 4.0.0 —— MIT，© Vanessa219 / B3log
- Apache ECharts —— Apache-2.0（含 NOTICE 义务，已保留）
- KaTeX **字体文件** —— SIL OFL 1.1（**非 MIT**）

更新记录：[`CHANGELOG.md`](CHANGELOG.md)（开发者版）、[`CHANGELOG_USER.md`](CHANGELOG_USER.md)（用户版）。
