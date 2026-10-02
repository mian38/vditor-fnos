# 版本归档与回滚

1.1.4 是 **1.1.x 系列的最终版本**，已冻结。1.2 开发全程在 `dev/v1.2` 分支进行，不影响 1.1.4 的回滚能力。

## 分支与标签

| 名称 | 类型 | 说明 |
| --- | --- | --- |
| `main` | 分支 | 最新开发版本 |
| `v1.1.x` | 分支 | 1.1.x 维护分支（已冻结，仅接受 bug 修复） |
| `dev/v1.2` | 分支 | 1.2 开发分支：移动端 API + Android 客户端 |
| `v1.1.4` | **标签** | 1.1.4 完整快照，不可变 |

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
