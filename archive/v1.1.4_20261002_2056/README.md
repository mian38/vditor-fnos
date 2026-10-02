# v1.1.4 — 1.1.x 系列最终版本（归档快照）

- **版本**：`1.1.4`（**1.1.x 系列的最终版本**，功能已冻结）
- **冻结时间**：2026-10-02 20:56
- **含义**：1.2 动手前的完整状态 = 1.1.4 功能修复 + 全量审计精简。
- **对应 Git 标签**：`v1.1.4`（首选回滚手段）；**维护分支**：`v1.1.x`

## 快照内容

| 文件 | 说明 |
| --- | --- |
| `server.py` | 后端主文件（1,906 行 / 80,936 字节），**含审计精简全部改动** |
| `vd_util.py` | 纯函数与常量（435 行 / 16,964 字节） |
| `index.html` | 单页前端（2,510 行 / 127,420 字节） |
| `manifest` | fnOS 应用元信息（`version = 1.1.4`） |
| `cmd/` `config/` `wizard/` | fnOS 生命周期脚本 / 权限配置 / 卸载向导 |
| `server.py` `vd_util.py` `install.sh` `config.env` | **nas 通用版**同名文件（`vditor-nas/`） |
| `CHANGELOG.md` `CHANGELOG_USER.md` | 该版本的完整变更记录（开发者版 / 用户版） |

> 完整前端资源（`vditor/`，360 文件 / 15.4 MB）**未包含**在本快照中——它与1.1.3 及之前各版**完全一致**，未做任何改动，需要时从 `vditor-fpk/app/vditor/` 直接取用即可。

## md5 校验

| 文件 | md5 |
| --- | --- |
| `server.py` | 见 `git show v1.1.4:vditor-fpk/app/server.py \| md5sum` |
| `vd_util.py` | 见 `git show v1.1.4:vditor-fpk/app/vd_util.py \| md5sum` |
| `index.html` | 见 `git show v1.1.4:vditor-fpk/app/index.html \| md5sum` |

## 对应产物

| 产物 | 字节 | md5 |
| --- | --- | --- |
| `releases/com.mian38.vditor_1.1.4.fpk` | 4,516,769 | `30a2d3fcecb592bc2a3bf587b8fea22d` |
| `releases/vditor-nas-1.1.4.tar.gz` | 4,470,136 | `4bf5fdc1ac6b3a0ac38cce064df6688c` |

## 相对 1.1.3 的变更（两批）

**第一批·功能修复**

1. 黑名单行「添加 / 恢复默认」按钮与输入框错位 —— CSS 特异性不足（0,1,1 被 0,2,1 压过），提升至 0,3,1。
2. 点「恢复默认」后无法保存 —— 默认清单含 `appref-ms`（连字符）被判非法 → 整次保存被拒，三处校验同步放宽。
3. 连带：含连字符的扩展名落盘后 404（`UPLOAD_NAME_RE` 同步放宽）。

**第二批 · 全量审计与精简**

4. **High 级缺陷修复**：4 处裸 `int(Content-Length)` 无异常保护 → 非法长度导致连接断开 + traceback。新增 `_content_length()` / `_read_body(handler, limit)` 统一入口。
5. 加固：`FAVICON_MAX_BYTES = 4MB`。
6. 精简：删死函数 `_env_bool`、13 个未用import、3 行空占位注释。
7. 抽取 8 个统一入口消除重复逻辑：`_build_headers` / `_fail_entry` / `_json_body` / `_apply_int_setting` / `split_ext_tokens` / `_paths_from_json` 等。

## 测试基线（回滚后应达到）

| 套件 | 结果 |
| --- | --- |
| `test_audit114.py`（全量 12 段） | **189/189** |
| `test_v114.py` | 37/37 |
| `test_v113.py` | 79/79 |
| `test_v112.py` | 30/30 |
| `test_smoke_pkg.py`（包内冒烟） | 53/53 |

## 回滚方式

**推荐（Git，零风险）**：

```bash
git checkout v1.1.x        # 切到 1.1.x 维护分支
# 或取回单个文件
git checkout v1.1.4 -- vditor-fpk/app/server.py
```

**离线（本目录）**：用本目录的 `server.py` / `vd_util.py` / `index.html` 覆盖 `vditor-fpk/app/` 同名文件，再同步到 `vditor-nas/`，然后重新 `fnpack.exe build -d vditor-fpk`。

## 只读声明

本目录**不参与任何构建**，仅供对比与回滚。