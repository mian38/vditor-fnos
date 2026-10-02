# 4.0.17 (beta) 源码归档

- **归档时间**：2026-10-02 10:22 (Asia/Shanghai)
- **源版本**：`4.0.17`（4.0.x β 迭代线最终版）
- **用途**：冻结 1.0 正式版动手前的完整状态，供回溯、比对与回滚。

## 内容

| 路径 | 说明 |
| --- | --- |
| `vditor-fpk/` | fnOS 应用**完整源码树**（app/ + cmd/ + config/ + wizard/ + manifest + 图标 + LICENSE），即 4.0.17 安装包的构建输入。 |
| `ui_style_v414.css` | 页面 `<style>` 区块的**唯一源**（`apply_style_v414` 用它整块替换 index.html 的样式）。 |
| `build_fpk.py` | 打包脚本（把 `vditor-fpk/app/` 打成 gzip tar）。 |
| `apply_style_v414` | 样式同步脚本（幂等 + 断言）。 |
| `check` / `check_css_clip.py` | 文案排版体检 / 工具栏裁剪回归守卫。 |
| `com.mian38.vditor_4.0.17-beta.fpk` | 该版本对应的安装包产物（与当时 `releases/` 内文件逐字节一致，md5 `dd6860f1b57037ee7612df8de7a34ebc`）。 |
| `legacy_patches/` | 4.0.x 期间的一次性补丁脚本（patch_*.py），已被 build/apply 工具取代，仅作历史留存。 |
| `legacy_tests/` | 早期开发用测试脚本（test_request4/4b、test_smoke2），已并入标准回归套件，仅作历史留存。 |
| `legacy_artifacts/` | 旧的官方 fnpack 构建与独立部署包（vditor-nas-4.0.0.tar.gz）等历史产物。 |

## 备注

- 本快照拷贝时统一**排除了 `__pycache__`**（Python 字节码，非源码）。
- 归档为纯目录（可读可 diff）；未压缩，便于直接检索。
- 该快照**不受**后续 1.0 版任何改动影响。
