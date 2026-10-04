# 版本归档与回滚

**当前主线 = `main` 分支。** 版本发布一律使用 **tag**（`v<major>.<minor>.<patch>`），
不按版本号创建长期分支，历史快照也只用 tag 保留。

## 分支与标签

### 分支

| 名称 | 说明 |
| --- | --- |
| `main` | **唯一分支，当前主线**。原 `v1.1.x` 分支于 2026-10-03 改名而来 |

已删除的历史分支（提交均由 tag 保留，可随时恢复）：

| 名称 | 说明 |
| --- | --- |
| ~~`dev/v1.2`~~ | 1.2 开发分支，已删除 |
| ~~`archive/v1.1.4beta`~~ | 1.1.4beta 归档分支，已删除；内容由标签 `v1.1.4beta` 完整保留 |

### 标签

正式版自 `1.0` 起，1.4.x 为当前系列（`v1.4.0` ~ `v1.4.3`）。
`4.0.x` 为早期 β 迭代线，`v1.1.4beta` 为已归档的移动端 API 实验线。
完整列表见 `git tag`。

## 分支管理规范

- **主分支固定 `main`**，禁止按版本号（`v1.x` / `v2.0`）建长期分支。
- **发版打 tag**，不在 `main` 上分叉版本分支。
- **短期功能/修复分支**：需要时从 `main` 拉 `feat/<scope>` / `fix/<scope>`，合并回 `main` 后**立即删除**。
- **历史快照以 tag 保存**，不建 `archive/*` 分支。
- 完整规范见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## v1.1.4beta 归档线说明

- **版本号由来**：该线内容基于 1.1.4 开发，曾误用 `1.2.0beta`，因与下一个 minor（`1.2.0`）冲突，已统一改号为 **`1.1.4beta`** 并归档。
- **归档内容**：移动端 API（`/api/m/*`）、`mobile_api.py`、API 数据输出开关 `api_output`。原生 Android 客户端在归档前**已彻底移除**。
- **恢复方式**（零破坏性，任选其一）：
  ```bash
  git checkout v1.1.4beta                                          # 切出归档快照（detached HEAD）
  git checkout v1.1.4beta -- vditor-fpk/app/mobile_api.py         # 只取回单个文件
  git show v1.1.4beta:docs/MOBILE_API.md                          # 直接查看归档版文档
  ```
  > `v1.1.4beta` 是 tag 而非分支，`git checkout` 后处于游离头指针；回到主线用 `git checkout main`。
- 文档：`docs/MOBILE_API.md` 在 `v1.1.4beta` 标签上是「已实现版」，在主线 `main` 上是「预留接口规范版」
  （当前服务端**无任何 `/api/m/` 路由**，调用会得到 404）。

## 回滚

```bash
# 取回任意历史版本的单个文件（最常用，零风险）
git checkout v1.4.2 -- vditor-fpk/app/index.html

# 查看历史版本某文件内容，不改动工作区
git show v1.4.2:vditor-fpk/app/server.py

# 整体回退到某标签（破坏性：先确认 git status 干净，并先建备份分支）
git branch backup-before-rollback && git reset --hard v1.4.2
```

## 本地备份（不纳入 Git）

以下目录**仅存在于本地工作区**，已被 `.gitignore` 排除，不会推送到仓库：

- `releases/` —— 构建产物（`.fpk`）。按项目约定默认本地保留，不主动清理。
- `archive/` —— 历史版本的文件级快照。**体积大且源码可用 Git 历史还原，故不分发**；
  如需查看某个旧版本的文件内容，用上面的 `git show` / `git checkout` 即可。
- `_audit_backup/` —— 审计/重构前的临时回滚备份。
