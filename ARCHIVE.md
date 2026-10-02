# 版本归档与回滚

1.1.4 是 **1.1.x 系列的最终版本**，已冻结。1.2 开发全程在 `dev/v1.2` 分支进行，不影响 1.1.4 的回滚能力。

## 分支与标签

| 名称 | 类型 | 说明 |
| --- | --- | --- |
| `main` | 分支 | 稳定版指针（当前停在 1.1.4） |
| `v1.1.x` | 分支 | 1.1.x 维护分支（已冻结，仅接受 bug 修复） |
| `dev/v1.2` | 分支 | **1.2 开发分支（当前分支）**：移动端 API + Android 客户端 |
| `v1.1.4` | **标签** | 1.1.4 完整快照，不可变 |
| `v1.2.0` | **标签** | 1.2.0 完整快照，不可变 |

## 回滚

```bash
# 切到 1.1.x 维护分支（推荐，零风险）
git checkout v1.1.x

# 取回 1.1.4 的单个文件
git checkout v1.1.4 -- vditor-fpk/app/server.py

# 取回 1.1.4 的 app 目录（不含 vditor/ 静态资源，体积大）
git checkout v1.1.4 -- vditor-fpk/app/server.py vditor-fpk/app/vd_util.py vditor-fpk/manifest

# 彻底丢弃 1.2 改动（破坏性：先确认 git status 干净）
git checkout v1.1.x
```

> **不建议** `git reset --hard v1.1.4` —— 那是把 1.2 分支的提交历史也抹掉。
> 1.2 已用`v1.2.0` 标签独立留存，切分支即可，**回滚不需要任何破坏性操作**。

## 版本对照

| 版本 | 标签 | 分支 | 产物 |
| --- | --- | --- | --- |
| 1.1.4 | `v1.1.4` | `v1.1.x` / `main` | `releases/com.mian38.vditor_1.1.4.fpk`（4,516,769 字节） |
| 1.2.0 | `v1.2.0` | `dev/v1.2` | `releases/com.mian38.vditor_1.2.0.fpk`（4,525,079 字节）<br>`releases/Vditor-1.2.0-release.apk`（1,385,604 字节） |

## 离线备份

`archive/v<版本>_<时间戳>/` 为文件级只读快照，各目录含 README 说明对应状态与回滚方式。
`releases/` 存放正式产物（`.fpk` / `.apk` / `.tar.gz` 均**未纳入 Git 跟踪**，见 `.gitignore`）。

**重要**：`.fpk` 与 `.apk` 不入库，只存在于 `releases/` 与 Git 标签之外。
换机器或仓库损坏后需重新构建：

```bash
# fpk
rm -rf vditor-fpk/app/__pycache__   # 打包前必须清
./fnpack.exe build -d vditor-fpk

# apk（需先备好 JDK 17 + Android SDK 34 + Gradle 8.7，见 android/README.md）
cd android && ./build_apk.sh release
```

详见 `archive/README.md`。
