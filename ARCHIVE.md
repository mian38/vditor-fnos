# 版本归档与回滚

**当前主线 = `v1.1.x`（版本 1.1.4）。**

1.1.4 是 **1.1.x 系列的最终版本**，已冻结，现重新作为主线继续迭代。
1.2 线已**转为 beta 归档**（`1.2.0beta`），不再作为主线维护，代码完整保留、可随时恢复。

## 分支与标签

| 名称 | 类型 | 说明 |
| --- | --- | --- |
| `v1.1.x` | 分支 | **当前主线**。1.1.x 维护分支（版本 1.1.4） |
| `main` | 分支 | 历史分支，停留在 `ebadb91`（= v1.1.4） |
| `dev/v1.2` | 分支 | 1.2 开发分支（已归档，不再推进） |
| `archive/v1.2.0beta` | 分支 | **1.2 归档分支**，指向 `9f206fd` |
| `v1.1.4` | **标签** | 1.1.4 完整快照，不可变 |
| `v1.2.0` | 标签 | 1.2 开发期快照（归档前的 1.2.0 状态） |
| `v1.2.0beta` | **标签** | **1.2 归档版**（版本号已统一为 `1.2.0beta`） |

## 1.2 归档线说明

- **归档内容**：移动端 API（`/api/m/*`，16 个接口）、`mobile_api.py`、API 数据输出开关 `api_output`、
  1.2.0 完整审计修复与精简。原生 Android 客户端在归档前**已彻底移除**（源码 / 构建脚本 / 产物 / 构建环境全删，释放 1.6 GB）。
- **恢复方式**（零破坏性，任选其一）：
  ```bash
  git checkout archive/v1.2.0beta        # 切到归档分支
  git checkout v1.2.0beta -- vditor-fpk/app/mobile_api.py   # 只取回单个文件
  git show v1.2.0beta:docs/MOBILE_API.md                     # 直接查看归档版文档
  ```
- 文档：`docs/MOBILE_API.md` 在 1.2 归档分支上是「已实现版」，在主线 `v1.1.x` 上是 1.1.3 的「预留接口规范版」（当时服务端无任何 `/api/m/` 路由）。

## 回滚

```bash
# 切到 1.1.x 维护分支（推荐，零风险）
git checkout v1.1.x

# 取回 1.1.4 的单个文件
git checkout v1.1.4 -- vditor-fpk/app/server.py

# 彻底丢弃 1.2 改动（破坏性：先确认 git status 干净）
git branch backup-before-rollback && git reset --hard v1.1.4
```

## 离线备份

`archive/v<版本>_<时间戳>/` 为文件级只读快照，各目录含 README 说明对应状态与回滚方式。
`releases/` 存放正式产物（`.fpk` 未纳入 Git 跟踪）。

详见 `archive/README.md`。
