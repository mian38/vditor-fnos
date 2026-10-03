# 并行安全机制（多 agent 协作）

本项目仅靠 WorkBuddy agent 推进开发，人工介入极少。为避免多个 agent 并发改仓库造成冲突或资源竞争，遵循以下纪律。

## 1. 分支纪律
- 唯一主线 `main`：**禁止多 agent 同时直接在 main 上改动**。
- 任何实质性修改都从 main 拉短期分支 `feat/<scope>` / `fix/<scope>`，合并回 main 后立即删除。
- 若确需在 main 上做极小改动，确保同一时刻只有一个 agent 在工作（见第 3 节锁机制）。

## 2. 工作前自检（preflight.sh）
每次动手前运行：

```bash
bash preflight.sh
```

输出 GO/NO-GO，检查项：
- 当前分支；
- 工作区是否干净（有未提交改动 → NO-GO，避免覆盖/冲突）；
- 相对 main 是否落后（落后 → 先 rebase，否则合并冲突）；
- 是否存在其他 agent 的独占锁。

## 3. 独占锁（防并发）
- 开始大块改动前：`bash preflight.sh --claim <你的 agent 标识>`
  写入 `.workbuddy/agent_lock`（含标识 + 时间，30 分钟有效）。若已有他人有效锁 → 拒绝。
- 改完后：`bash preflight.sh --release <同一标识>` 释放锁。
- 锁文件位于 `.workbuddy/`（已在 .gitignore），不会进仓库。

## 4. 测试套件（精简后）
重写后的测试仅 5 个文件，覆盖核心功能与打包，全部动态读取版本、升版不假红：

| 文件 | 覆盖范围 |
| --- | --- |
| `test_version.py` | 版本号一致性（manifest ↔ server，语义化版本，不低于基线） |
| `test_security.py` | 安全/正确性原语：上传黑名单、扩展名归一、路径穿越、私网 IP、multipart、版本键、共享路径 |
| `test_cli.py` | 生命周期脚本语法校验（cmd/*、app/bin/vditor） |
| `test_pkg.py` | 安装包结构 + 版本一致性（校验源码树 + 可选真实 fpk） |
| `test_core.py` | 核心功能端到端（启动一次服务，覆盖鉴权/CRUD/版本/分区/备份/设置/静态安全/上传） |

打包门禁：`rm -rf vditor-fpk/app/__pycache__` 后运行 `python test_pkg.py && python test_core.py`。

## 5. 冲突高发文件
`main` 合并时高危：`manifest`、`vditor-fpk/app/server.py`、`vditor-fpk/app/index.html`。
改动这些文件务必先在独立分支、跑对应定向测试，再合并。
