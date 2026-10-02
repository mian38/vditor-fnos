# 1.1.2 源码归档

- **归档时间**：2026-10-02 18:52 (Asia/Shanghai)
- **源版本**：`1.1.2`（1.1.x 正式版）
- **用途**：冻结 1.1.3 动手前的完整状态，供回溯、比对与回滚。

## 内容

| 路径 | 说明 |
| --- | --- |
| `vditor-fpk/` | fnOS 应用**完整源码树**（app/ + cmd/ + config/ + wizard/ + manifest + 图标），即 1.1.2 安装包的构建输入（唯一源）。 |
| `vditor-nas/` | 通用 Linux 部署版，由 `vditor-fpk/app` 经 `make_nas.py` 自动派生。 |
| `make_nas.py` | 由 `vditor-fpk/app` 派生 `vditor-nas/` 的生成脚本。 |
| `bump_version.py` | 版本号一键同步（manifest / 两处 `APP_VERSION` / tests 硬编码断言）。 |
| `com.mian38.vditor_1.1.2.fpk` | 该版本对应的安装包产物（与 `releases/` 内文件逐字节一致，md5 `2f45c83e2f98f88a1656319c4465c2ac`）。 |

## 本版本要点（供回溯参考）

1.1.2 相对 1.1.1 的主要变化：

- **上传限制放开 + 可调**（首次引入 `upload_max_mb` / `upload_accept` 两个设置项，白名单机制）。
- **网络安全两项默认开启**（`trust_proxy` / `secure_cookie` 默认 True，手动关闭需二次确认）。
- **解除 `secure_cookie` 关闭时的公网 HTTP 限制**。
- 外观设置「暗黑模式」改名「深色模式」；网页图标说明更新；卸载引导文案重写。

> 注：本次归档后，1.1.3 将把上传格式校验由**白名单反转为黑名单**机制，
> 因此 1.1.2 的 `upload_accept` 语义与 1.1.3 的 `upload_deny` 不同，回滚时需注意。

## 备注

- 本快照拷贝时统一**排除了 `__pycache__`**（Python 字节码，非源码）。
- 归档为纯目录（可读可 diff）；未压缩，便于直接检索。
- 已用 `diff -r` 校验与当时工作区**完全一致**；`.fpk` 以 md5 比对确认逐字节一致。
- 该快照**不受**后续 1.1.3 版任何改动影响。