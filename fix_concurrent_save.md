# 修复方案：多浏览器实例并发保存导致覆盖 / 丢失 / 损坏

> 目标读者：负责实施本修复的 agent。本文档描述根因、最小修复思路、具体实现步骤与注意事项，可直接照做。
> 范围：**仅后端 `vditor-fpk/app/server.py`，零第三方依赖，不改前端、不改接口契约**。
> 对应分析见 `.workbuddy/memory/2026-10-23.md`。

---

## 1. 问题根因

同一文档被多个浏览器标签页（或多个实例）同时触发保存时，存在数据风险。代码事实（均已核对 `server.py`）：

- **保存入口**：`do_POST` → `p == "/api/save"` → `_api_save`（约 `server.py:1522`）。
- **写盘方式**：`with open(fp, "w", encoding="utf-8") as f: f.write(content)`（约 `server.py:1555-1556`）——**直接「截断 + 写入」，非原子**。
- **无锁**：全局仅 `LOG_LOCK`（`server.py:129`，仅保护 `login_log.json`）；`FAIL_LOG`/`is_locked` 是登录防暴破，与写文件无关；保存路径**无任何互斥**。
- **并发模型**：`ThreadingHTTPServer`（`server.py:50, :2337`）——**每请求独立线程**，多 tab 同文档并发保存会真正并行进入 `_api_save`。
- **无乐观并发控制**：`_api_save` 不接收/不校验 base 版本或内容 hash；「历史版本」只做「覆盖前把旧内容归档」（`save_file_version`, `:694`），不是并发保护；自动保存超 `VERSION_SKIP_BYTES` 时连版本都不记。

**危险竞态**（tab A、B 打开同一文档，各改一段，几乎同时保存）：
1. A 读 `prev = v1`；B 读 `prev = v1`（两者都在任一方写入前读到同一旧版）。
2. A `open("w")` 截断 → 写 `v2`；B `open("w")` 截断 → 写 `v3`。
3. 磁盘最终 = `v3`（最后写者胜）→ **A 的 `v2` 被静默覆盖**。
4. 版本归档两处都存的是 `v1` → **`v2` 既非当前、也未被历史版本捕获，彻底丢失且不可恢复**。
5. 截断 + 非原子写还可能在重叠窗口留下**半截/交错损坏内容**。

**结论**：代码既无文件锁、也无原子写、更无版本/校验和类并发控制 → 同文档并发保存确有覆盖、丢失、损坏风险。不同文档多 tab 各自 `fp` 不同，互不干扰、安全。

---

## 2. 修复思路（最小改动）

用**最少改动**消除三类风险，采用纯后端两步法：

1. **全局保存锁 `SAVE_LOCK`**：把「读旧内容 → 归档历史版本 → 写文件」整体包成一个临界区。串行化后，B 必然在 A 写完后才读 `prev`，从而把 A 的 `v2` 归档为历史版本，最终 `v3` 为当前、`v2` 可恢复——**丢失与覆盖风险同时消除**。
2. **原子写**：写盘由「直接 `open("w")`」改为「写临时文件 + `os.replace` 原地替换」。保证任何时刻读到的都是完整旧文件或完整新文件，**杜绝半截/交错损坏**。

**为什么不引入乐观并发（ETag / base hash）**：那需要前端配合（保存前带 base 版本、收到冲突 409 后提示用户），改动面更大；在本应用（单用户 NAS、保存低频、文件小）规模下，锁 + 原子写已彻底消除风险，符合「最小且简单」原则。乐观并发仅作为可选增强列于 §3 步骤 3。

---

## 3. 具体实现步骤

### 步骤 1：新增全局保存锁（server.py，约 `:129` `LOG_LOCK` 定义处附近）

`threading` 已在文件顶部导入（现有 `LOG_LOCK` 已使用，无需新增 import）。在其旁加一行：

```python
SAVE_LOCK = threading.Lock()  # 保护文档保存的「读旧内容→归档历史版本→写文件」临界区
```

### 步骤 2：改写 `_api_save` 临界区（server.py，约 `:1538-1556`）

把从「`if os.path.isfile(fp) and SETTINGS.get("versioning"):`」到「`f.write(content)`」整段用 `with SAVE_LOCK:` 包裹，并将写盘改为原子写。**近似最终代码**：

```python
        try:
            parent = os.path.dirname(fp)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with SAVE_LOCK:
                # 版本快照必须在锁内读旧内容，保证与随后写入彼此一致
                if os.path.isfile(fp) and SETTINGS.get("versioning"):
                    try:
                        if manual or os.path.getsize(fp) <= VERSION_SKIP_BYTES:
                            with open(fp, "rb") as f:
                                prev = f.read()
                            if prev and prev != content.encode("utf-8"):
                                save_file_version(root["path"], rel_stored, prev, manual=manual)
                    except OSError:
                        pass
                # 原子写：临时文件 + 同目录 os.replace，避免读到半截文件
                tmp = "%s.tmp.%d.%d" % (fp, os.getpid(), int(time.time() * 1000))
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(content)
                os.replace(tmp, fp)
            invalidate_files_cache()
            st = os.stat(fp)
            self._send_json({"ok": True, "root": root_id, "path": rel_stored,
                             "abspath": os.path.abspath(fp), "mtime": int(st.st_mtime)})
        except OSError as e:
            self._send_json({"ok": False, "error": str(e)}, 500)
```

要点：
- 临时文件名带 `pid + 时间戳`，避免同一进程内并发同名冲突；**临时文件与最终文件同目录**（`fp + ".tmp..."`），`os.replace` 在同目录为原子操作（POSIX 与 Windows 均保证）。
- `invalidate_files_cache()` 放在锁内写盘之后，使缓存与磁盘一致。
- `save_file_version` 内部的 `os.remove` 清理超额版本也随整段进入临界区，无需额外处理。

### 步骤 3（可选增强，默认不做）：乐观并发

若未来需要多端协同更强一致性，可加：后端 `/api/save` 接受可选 `base_mtime`（或内容 hash）字段；若提供且与磁盘当前不一致，返回 `{"ok": False, "conflict": True, "current_mtime": ...}`；前端保存前记录上次保存 mtime，收到 conflict 时提示「文档已在别处被修改，是否覆盖 / 重载」。**本最小方案不包含此步。**

### 步骤 4：版本号与测试门禁

- 本改动属 **bug 修复** → 按 `AGENTS.md §1` 升 **z**：若 `1.5.0` 已发布，下一个为 `1.5.1`；迭代期用四段式 `1.5.1.N` 测试版。用 `tools/bump_version.py` 同步 `vditor-fpk/manifest` 的 `version=` 与 `server.py` 的 `APP_VERSION`，两源一致。
- 改动 `vditor-fpk/app/` 后至少跑 `python tests/test_pkg.py && python tests/test_core.py`。
- 交付前必须 `rm -rf vditor-fpk/app/__pycache__ && python tests/run_all.py --all` → **0 失败**。

---

## 4. 测试建议（防回归）

新增 `tests/test_concurrent_save.py`，并登记进 `tests/run_all.py` 的 `CASES`（不要散落别处）。

用例：本地起服务后，**并发**向同一文档发两个 `/api/save`（相同 `root`/`path`、不同 `content`）。断言：
1. 最终磁盘文件内容 == 其中一个请求的 `content`（无损坏、无交错）；
2. 该文档历史版本目录存在且 **≥ 1** 个版本（败者内容被归档，可恢复）；
3. 重复压测（如 10 轮 × 2 并发）不稳定失败。

**按 `AGENTS.md §2` 先复现再验证**：先在该测试存在时**临时移除锁/原子写**（即旧逻辑）确认测试能抓到 bug（出现损坏或版本缺失），再恢复修复确认通过。严禁「测试全绿但没验证它能抓到 bug」。

---

## 5. 注意事项

- **零第三方依赖**：仅用标准库 `threading` / `os`，不引入任何 pip 包；`server.py` 顶部 `sys.path.insert(0, …)` 自举保留。
- **SPDX**：本改动不新增文件，`server.py` 已有 SPDX 头，无需补；若新建测试文件，须加两行 `# Copyright (c) 2026 mian38` + `# SPDX-License-Identifier: MIT`。
- **锁粒度**：全局 `SAVE_LOCK` 对所有保存串行化。本应用为单用户 NAS、保存低频、文件小，性能影响可忽略；若未来需更高并发，可改为按文档 key 的 `dict` + `threading.Lock`（需清理逻辑），但**非必需**。
- **`os.replace` 原子性依赖同目录**：临时文件须与 `fp` 同目录（当前写法已满足），跨文件系统 rename 非原子，勿改路径。
- **不改前端**：本方案纯后端，前端无感知，接口契约不变。
- **文档/宣传**：属 bug 修复，不新增用户可见能力；用户版 changelog 用「修复」类，勿夸大。
- **人在环门禁**：agent 完成修复 + 测试 + 打包后，交付物一律为**未发布测试版**（四段式版本号），实机验证由用户（mian38）完成；agent 不自行打 tag / 建 Release / 上传。
