# 贡献指南

感谢你愿意为本项目付出时间。这份文档说明从提交 Issue 到合并代码的完整流程与约定。

参与本项目即表示你同意遵守 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。

---

## 目录

- [提交 Issue](#提交-issue)
- [安全漏洞](#安全漏洞)
- [开发环境](#开发环境)
- [代码结构约定](#代码结构约定)
- [提交规范](#提交规范)
- [测试约定](#测试约定)
- [派生副本纪律](#派生副本纪律)
- [升版本流程](#升版本流程)
- [许可](#许可)

---

## 提交 Issue

**请先搜索已有 issue**，避免重复。

| 类型 | 适合提交的内容 |
| --- | --- |
| Bug 反馈 | 复现步骤、实际结果、期望结果、环境（fnOS 版本 / Python 版本 / 浏览器） |
| 功能建议 | 描述使用场景，说明为什么需要它 |
| 文档纠错 | 指出错误内容与正确表述 |
| 提问 | 使用 Discussions 更合适 |

**Bug 反馈请务必附上**：fnOS 版本、Python 版本、浏览器版本、相关配置（**请勿贴出密码或哈希**）。

---

## 安全漏洞

**不要**通过公开 issue 报告安全问题。本项目处理密码与会话数据，漏洞细节公开可能
让未打补丁的用户暴露。报告方式见 [`SECURITY.md`](SECURITY.md)。

---

## 开发环境

**零第三方依赖**是本项目的硬性约束，请勿引入任何 `pip` 包。

- Python 3.8+
- 无需虚拟环境、无需 `pip install`、无需 Node.js

### 获取源码

```bash
git clone https://github.com/mian38/vditor-nas.git
cd vditor-nas
```

---

## 代码结构约定

### 单一源 + 派生副本

这是本项目**最容易踩坑**的地方，务必理解：

| 目录 | 角色 | 能否手工修改 |
| --- | --- | --- |
| `vditor-fpk/app/` | **唯一源** | ✅ 可以 |
| `vditor-nas/` | 派生副本 | ❌ **绝对不行** |

`vditor-nas/` 全部内容由 `make_nas.py` 从 `vditor-fpk/app/` + `nas-template/` 生成。
手工改派生副本会在下次生成时被覆盖。

### 模块职责

- `vd_util.py` —— **纯函数与常量**，无副作用、不持有可变状态
  （`EXTRA_MIME` / `MAX_*` / `UPLOAD_*` / `upload_headers` / `safe_join` / `parse_multipart` …）
- `server.py` —— HTTP 处理、认证、会话，**可变状态必须留在这里**
  （`SETTINGS` / `SESSIONS` / `DOC_ROOTS` / `PWHASH`）

把可变状态误放进 `vd_util.py` 会引入跨请求污染风险。

### 必须保留的自举代码

`server.py` 顶部必须保留：

```python
sys.path.insert(0, ...)
```

引入 `vd_util` 后，若服务被以 `-c` 或 `-m` 方式拉起，缺少这行会直接
`ModuleNotFoundError` 导致整站起不来。

### 前端样式

- 样式源唯一：`ui_style_v414.css` 是唯一的 `<style>` 源
- 运行时由 `apply_style_v414` 整块替换
- 新增 CSS 必须同时写进源文件，并补上对应的 MUST 断言

### 请求体读取（安全红线）

**只有两个合法入口**，禁止裸写 `int(self.headers.get("Content-Length", 0))`
或 `self.rfile.read()`：

```python
_content_length(handler)        # 非法/负数归一为 0
_read_body(handler, limit)      # 必须带 limit；缺失/非法/超限返回 b""
```

原因：已登录态下 `Content-Length: abc` 会抛未捕获 `ValueError`，连接直接断开。
请求体上限判断统一走 `MAX_BODY_BYTES`(64M) / `MAX_UPLOAD_BYTES`(512M) /
`BACKUP_MAX_BYTES`(512M) → 返回 413 并关闭连接。

### Vditor 集成要点

- **i18n 必须内联**：把 `zh_CN.js` 的扁平对象作为 `i18n` 选项传入 `new Vditor(...)`。
  改回外部 fetch 会导致线上深层静态路径 404、编辑器不显示。
- **线上只加载 `index.min.js`**（不是 `index.js`）
- 移动端下拉面板：**仅面板用 `position: fixed`**，工具栏的 `overflow` 不可改
- CSS 胜负靠**特异性**，不靠顺序；写测试断言时也不要按出现顺序判胜负

---

## 提交规范

分支命名：

| 前缀 | 用途 |
| --- | --- |
| `feat/` | 新功能 |
| `fix/` |缺陷修复 |
| `docs/` | 文档 |
| `chore/` | 构建、工具、杂项 |
| `audit/` | 代码审计与整改 |

提交信息采用前缀式：

```
feat: 新增文件历史版本 diff 视图
fix: 修复黑名单行按钮与输入框错位
docs: 补1.2 归档线恢复说明
chore(1.1.4): 版本号统一更新
```

类型：`feat` / `fix` / `docs` / `style` / `refactor` / `perf` / `test` / `chore` / `audit`

---

## 测试约定

**测试脚本自带计数器，直接运行，不需要 pytest**：

```bash
python test_v114.py         # 定向测试
python test_audit114.py     # 全量回归
python test_smoke_pkg.py    # 包内资源冒烟
```

写 HTTP 测试用例的两条硬规则（踩过坑，请务必遵守）：

1. **URL 参数必须 `encodeURIComponent`** —— 含中文的 `root` / `path` 直拼会得到
   404 假失败（请求行是 latin-1，中文还需 `quote` 包装）
2. **起长驻服务用 `Popen` + 轮询端口 + `terminate()`** —— 不要用
   `subprocess.run(timeout=)`，必然 `TimeoutExpired`

另外：`request()` 助手不能无条件覆写 `Content-Length`（用 `if "Content-Length" not in h`），
否则故意声明的超大值会被覆盖，导致超限测试失效。

**测试范围**：自 1.1.1 起只对**本轮修改**做定向测试，不再全量回归。
但改动 `vditor-fpk/app/` 后必须跑 `test_smoke_pkg.py`（改静态服务或精简包体时必跑）。

---

## 派生副本纪律

改完 `vditor-fpk/app/` 下的任何文件后，**必须**：

```bash
python make_nas.py
```

该脚本自带 `filecmp` 逐字节自检与 import 覆盖自检，输出 `OK 已生成` 才算成功。

打包前还需清理：

```bash
rm -rf vditor-fpk/app/__pycache__
```

---

## 升版本流程

版本号存于三处，`bump_version.py` 会一次性同步：

- `vditor-fpk/manifest` 的 `version=`
- `vditor-fpk/app/server.py` 与 `vditor-nas/server.py` 的 `APP_VERSION`
- `test_v406.py` / `test_v407.py` 的硬编码断言

```bash
python bump_version.py 1.1.5 --dry-run
python bump_version.py 1.1.5
```

**两份更新记录必须同时更新**：

- `CHANGELOG.md` —— 开发者版，含技术细节、根因分析、包体表
- `CHANGELOG_USER.md` —— 用户版，只讲「发生了什么变化」

用户版规范：标题 `## 版本号（YYYY-MM-DD）· 正式版/测试版`，按版本从新到旧，
内容仅归入**新增 / 修复 / 优化 / 更改**四个分点（空分点省略），禁开发者术语。

---

## 许可

你的贡献将以 MIT 许可发布。提交即表示你同意将贡献内容按该许可授权。

贡献代码中若复制了第三方代码片段，请**在PR 中说明来源与许可**，并在
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) 中登记。
