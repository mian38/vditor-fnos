# v1.2.0 快照（2026-10-02 22:00）

## 这是什么

1.2.0 正式版的**文件级只读快照**，用于离线备份与紧急回滚。
**只读，不参与构建**（`make_nas.py` 与 `fnpack.exe` 均不读此目录）。

对应 Git 标签：`v1.2.0`（提交 `ff3cf5d`）。
需要更精细的单文件回滚时优先用 Git，本目录用于「Git 不可用 / 仓库损坏」的场景。

## 文件清单

| 文件 | 说明 |
| --- | --- |
| `server.py` | 后端主文件（1,906 → 约 2,600 行），含 `/api/m/` 全部 15 个接口 |
| `mobile_api.py` | **1.2.0 新增**：移动端 API 纯逻辑层（响应包 / 错误码 / 参数校验） |
| `vd_util.py` | 纯函数与常量层（1.1.4 起沿用，未改动） |
| `index.html` | Web 前端（**本版本未改动**，127,420 字节） |
| `manifest` | fnOS 清单，`version=1.2.0` |
| `cmd/` `config/` `wizard/` | fnOS 生命周期脚本 / 默认配置 / 卸载向导 |
| `install.sh` `config.env` | nas 通用版部署脚本与环境模板 |
| `CHANGELOG.md` `CHANGELOG_USER.md` | 双更新记录（开发者版 / 用户版） |
| `MOBILE_API.md` | 移动端 API 规范（已实现版，含 curl 示例） |
| `README.md` | 项目说明 |

**未包含**：`vditor/` 静态资源（360 文件 / 约 15MB，体积过大不入快照）。
需要时从 `v1.2.0` 标签取：`git checkout v1.2.0 -- vditor-fpk/app/vditor`。
`index.html` 已在快照内（它强依赖 `vditor/`，缺一不可）。

## 产物

| 文件 | 大小 | md5 |
| --- | --- | --- |
| `releases/com.mian38.vditor_1.2.0.fpk` | 4,525,079 字节 | 见 `releases/` |
| `releases/vditor-nas-1.2.0.tar.gz` | 4,505,084 字节 | — |
| `releases/Vditor-1.2.0-release.apk` | 1,385,604 字节 | 签名有效（RSA 2048 / v2 scheme） |

## 本版本的两处修复（回滚到 1.1.4 会失去）

1. **登出幂等**：`POST /api/m/auth/logout` 对已失效 token 回 401 → 改为回 `ok`。
2. **`make_nas.py` 漏登记模块**：生成的 nas 版会 `ModuleNotFoundError` 起不来 →
   补登记 + 新增 `check_imports_covered()` 守护。

## 回滚到 1.1.4

见仓库根目录 `ARCHIVE.md`。最简路径：

```bash
git checkout v1.1.x
```

或用本目录的文件手工覆盖（**不建议**，容易漏文件）：

```bash
cp archive/v1.1.4_20261002_2056/{server.py,vd_util.py,manifest} vditor-fpk/app/ 2>/dev/null
# 注意：manifest 应放vditor-fpk/ 而非 app/
```
