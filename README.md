# Vditor for NAS

把开源 Markdown 编辑器 [Vditor](https://github.com/Vditor/Vditor) 打包成一个**无需 Docker** 的轻量 Web 应用，部署到 NAS 后浏览器打开即用。

- 纯静态前端 + 一个用 Python 内置标准库写的微型服务器（**零第三方依赖**）
- 非Docker 部署，由系统进程直接运行，不依赖容器
- 密码登录 + 会话 Cookie，防暴力破解、防会话劫持
- 文档直接落盘到 NAS 目录，可经 SMB / FTP 直接访问
- 跨平台：飞牛 fnOS、群晖、极空间、任意带 Python 3 的 Linux

**当前版本：1.1.4** ｜ 许可：[MIT](LICENSE)

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
3. 按安装向导设置访问端口与文档目录
4. 安装完成后浏览器访问 `http://<NAS IP>:<端口>`

### 方式 B：通用 Linux（NAS 通用版）

适用于任意带 Python 3 的 Linux（群晖、极空间、树莓派等）：

```bash
# 1. 上传 vditor-nas-<版本>.tar.gz 到 NAS 并解压
tar -xzf vditor-nas-<版本>.tar.gz -C /tmp
cd /tmp/vditor-nas

# 2. 运行安装脚本（可指定端口，默认 3838）
sudo bash install.sh /opt/vditor-nas 3838
```

脚本会安装到 `/opt/vditor-nas`、注册 systemd 服务并设置开机自启。

**手动运行**（无 systemd 环境亦可）：

```bash
cd /opt/vditor-nas
python3 server.py
```

**卸载**：

```bash
sudo bash /opt/vditor-nas/uninstall.sh
```

> 卸载会删除安装目录（含已上传文件与文档），请先备份。

部署细节详见 [`nas-template/README.md`](nas-template/README.md)。

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

本仓库采用「单一源 + 派生副本」结构：

- `vditor-fpk/app/` —— **唯一源**，后端与前端的真实来源
- `vditor-nas/` —— **派生副本**，由 `make_nas.py` 自动生成，**请勿手工修改**
- `vditor-fpk/` —— fnOS 打包源目录

改动后端或前端后，必须重新生成派生副本：

```bash
python make_nas.py      # 逐字节自检 + import覆盖自检
```

### 构建 fnOS 安装包

`fnpack.exe` 需从[飞牛官方获取](https://www.fnnas.com)，不随本仓库分发。

```bash
rm -rf vditor-fpk/app/__pycache__
fnpack.exe build -d vditor-fpk
```

### 升版本号

版本号存于三处，`bump_version.py` 会一次性同步：

```bash
python bump_version.py 1.1.5 --dry-run   # 先预览
python bump_version.py 1.1.5             # 确认后执行
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
├── vditor-nas/               # 派生：通用 Linux 版（勿手工改）
├── nas-template/            # NAS 部署模板（install.sh 等）
├── docs/                    # 文档
├── test_*.py                # 回归测试
├── make_nas.py              # 派生脚本
├── bump_version.py          # 版本号同步
└── build_fpk.py             # fpk 构建
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

## 许可

本项目源码采用 [MIT 许可](LICENSE)，Copyright (c) 2026 mian38。

随包分发的第三方组件保留各自许可，**不在本项目 MIT 许可覆盖范围内**，
完整清单见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

其中需特别注意：

- 编辑器内核 Vditor 4.0.0 —— MIT，© Vanessa219 / B3log
- Apache ECharts —— Apache-2.0（含 NOTICE 义务，已保留）
- KaTeX **字体文件** —— SIL OFL 1.1（**非 MIT**）

更新记录：[`CHANGELOG.md`](CHANGELOG.md)（开发者版）、[`CHANGELOG_USER.md`](CHANGELOG_USER.md)（用户版）。
