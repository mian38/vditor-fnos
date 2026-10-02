# vditor 1.1.4 · 审计前状态（pre-audit 快照）

- **冻结时间**：2026-10-02 20:30
- **含义**：1.1.4 **首轮**（两项功能 bug 已修）完成后、**全量审计与精简之前**的代码状态。
- **为什么保留**：1.1.4 审计精简是同版本内的二次修订（版本号不变），此快照是回滚到「只含功能修复、不含审计改动」的唯一依据。

## 文件

| 文件 | 行数 | 字节 | md5 |
| --- | --- | --- | --- |
| `server.py` | 1,910 | 80,285 | `37c62d7502f06fd6cee9f52bb199b9bb` |
| `vd_util.py` | 417 | 16,192 | `165dc17df6df8239e7767f74aec5429e` |
| `index.html` | 2,510 | 127,420 | `63d5573bce15f7f90fd17454c8e20656` |

> `index.html` 在审计中**未做任何改动**，md5 与交付版一致。

## 此快照尚未包含的审计改动

1. **High 级修复**：4 处裸 `int(Content-Length)` 未保护（`/api/upload`、`/api/favicon`、`/api/backup/restore`、`do_POST`）→ 会抛未捕获 `ValueError`、连接直接断开 + traceback。
2. **加固**：`FAVICON_MAX_BYTES = 4MB`。
3. **精简**：删死函数 `_env_bool`、清 13 个未用 import、删 3 行空占位注释。
4. **抽取统一入口**（8 个）：`_content_length` / `_read_body` / `_build_headers` / `_fail_entry` / `_json_body` / `_apply_int_setting` / `split_ext_tokens` / `_paths_from_json`。

## 对应产物

| 产物 | 字节 | md5 |
| --- | --- | --- |
| `releases/com.mian38.vditor_1.1.4.fpk`（审计前，已被覆盖） | 4,521,423 | `9cd99be0be1cd767fe679f49c3a3da64` |

## 回滚方式

用本目录的 3 个文件覆盖 `vditor-fpk/app/` 同名文件，再 `shutil.copy2` 同步到 `vditor-nas/`，然后重新 `fnpack.exe build -d vditor-fpk`。

> 注意：回滚会**重新引入 High 级缺陷**，仅在极端情况下使用。

## 只读声明

本目录**不参与任何构建**，仅供对比与回滚。