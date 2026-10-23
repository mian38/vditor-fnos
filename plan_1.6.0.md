# 1.6.0 开发方案（合并三需求，供 agent 直接参照开发）

> 适用范围：本方案覆盖将纳入 **1.6.0** 的三个需求。
> - ① **并发保存修复**（bug 修复）：同一文档被多浏览器实例同时保存时覆盖/丢失/损坏。详细根因与伪代码见同目录 `fix_concurrent_save.md`，本文档为合并视图。
> - ② **顶栏文件名显示优化**（新能力）：长文件名自适应 + 仅文件名文本自身横向滚动。
> - ③ **文档查找与替换**（新能力）：当前文档的查找/替换面板。
> 唯一源：`vditor-fpk/app/`（`server.py` 后端 + `index.html` 前端）。硬约束：零第三方依赖、纯标准库、SPDX、人在环发版门禁。

---

## 0. 范围与版本

- **版本判定**：② 与 ③ 均为用户可见新能力 → 按 `AGENTS.md §1` 升 **y**，`1.5.0 → 1.6.0`（`z` 归零）。① 属 bug 修复，本应按 `z` 单独发 `1.5.1`，但本轮回合并入 1.6.0 一并交付，**不另发 1.5.1**。
- **迭代期版本号**：四段式 `1.6.0.N`（`N` 从 1 递增），每次构建严格递增以便 fnOS 覆盖安装；四位一律视为测试版，禁对外发布。
- **同步两源**：`tools/bump_version.py` 同步 `vditor-fpk/manifest` 的 `version=` 与 `server.py` 的 `APP_VERSION`。

---

## 1. 需求一：并发保存修复（后端 `server.py`）

**根因**（已核实）：`_api_save`（约 `server.py:1522`）写盘为 `open(fp,"w")` 截断后写（:1555-1556），**非原子**；保存路径**无任何锁**（仅 `LOG_LOCK` :129 保护登录日志）；`ThreadingHTTPServer`（:50,:2337）每请求一线程，多 tab 同文档并发保存会真正并行进入临界区；`_api_save` 不校验 base 版本/校验和，无乐观并发控制。后果：后写覆盖先写、数据不可恢复丢失、截断窗口内文件半截/交错损坏。

**最小修复**（纯后端、零新增依赖）：
1. 新增全局 `SAVE_LOCK = threading.Lock()`（与 `LOG_LOCK` 同处）。
2. 把「读旧内容 → 归档历史版本 → 写文件」整体用 `with SAVE_LOCK:` 包裹；写盘改「临时文件 + `os.replace` 同目录原子替换」（临时文件名带 `pid+时间戳` 防同名）。
3. 不引入前端改动、不做乐观并发（列为可选增强）。

**验收**：并发发两个同文档 `/api/save`（不同 content），最终文件 == 其一且无损坏；历史版本目录 ≥1 个（败者内容可恢复）；压测稳定。完整步骤与伪代码见 `fix_concurrent_save.md`。

---

## 2. 需求二：顶栏文件名显示优化（前端 `index.html`）

**涉及模块**：内联 `<style>`（约 129–132、593、821–823 行）+ JS（文件名更新点约 2631 行 `getElementById('cur-name')`）。
**现状**（已核实）：顶栏 `#topbar`(flex 行) 含 `#btn-toggle-side`、`span.fname`（"当前文件："+`<b id="cur-name">`）、`#word-counter`、`.top-actions`（按钮组含主按钮 `#btn-save`）。`#topbar .fname`（:130）当前 `flex:0 0 auto`（不收缩），且 `#topbar::-webkit-scrollbar{height:0}`（:129）说明顶栏曾允许横向滚动——须彻底禁止。

**实现**：
- CSS：`#topbar { overflow:hidden }`（彻底禁滚动）；`#topbar .fname` 改 `flex:1 1 auto; min-width:0; overflow:hidden;`（允许收缩并裁剪）；`#cur-name` 新增 `display:inline-block; max-width:100%; overflow:hidden; white-space:nowrap;`；`.top-actions` 及内部按钮加 `flex:0 0 auto; flex-shrink:0;`（永不被挤压）。注：`.fname` 在 593 行另有通用规则，改动以 `#topbar .fname` 作用域为准。
- JS（新增 `updateFilenameScroll()`）：比较 `#cur-name` 的 `scrollWidth`/`clientWidth`，仅溢出时启动横向自动滚动（rAF 驱动 `transform:translateX` 在 `[0,-(overflow)]` 往返）；`mouseenter` 暂停、`mouseleave` 恢复；非溢出清除动画并复位。在 2631 行更新 `cur-name` 处调用。

**交互/边界**：
- 空间充足完整显示、无滚动；不足时仅 `#cur-name` 文本自身滚动，前缀与按钮静止。
- **窗口 resize**：`ResizeObserver` 监听 `.fname` 重测重排（同时覆盖浏览器缩放引起的尺寸变化）。
- **切换文件**：重置+重测。
- **悬停暂停**：`mouseenter/leave`。
- **低分辨率/高缩放**：同一套自适应；极端窄屏靠按钮 `flex-shrink:0` 保可见，必要时在既有响应式媒体查询隐藏 `#word-counter`（可选）。

**验收**：长文件名下顶栏整体不滚动/不溢出；按钮始终完整可点、不被遮挡；仅文件名文本横向滚动、悬停暂停；缩放/缩窗/切文件表现一致。

---

## 3. 需求三：查找与替换（前端 `index.html`）

**Vditor 上游核查结论**：`vditor/dist/method.min.js` 公开方法仅见 `getCode`/`getElements` 等，**无 `search`/`find`/`replace` 公开方法**；应用 toolbar 配置未含 search；grep 命中的 `search`/`replace` 均为内部 `String.replace` 与 lute 渲染字样。结论：**Vditor 未提供可用查找/替换，必须自建**（实施前建议再以 Vditor 官方文档按当前 4.0.0 复核一次）。

**涉及模块**：新增查找/替换面板 DOM（复用既有模态/内联条样式；按钮挂 `btn--ghost`/`btn--primary` 变体类，遵循 `AGENTS.md §2.1`；`#confirm-mask` 反色规则不碰）、`.vd-find`(`<mark>`) 高亮样式；新增 JS 模块（快捷键/匹配/高亮/替换）。复用 `getContent()`/`setContent()` 访问层与全局 `vditor` 实例（约 1894 行 `let vditor = null;`）。

**实现（推荐混合方案，含降级）**：
- **查找（视觉）**：遍历 Vditor 渲染内容区（IR/所见即所得为 `.vditor-reset`，源码模式为 `.vditor-textarea`/`pre`）文本节点，命中处用 `<mark class="vd-find">` 包裹；当前命中 `.vd-find-current` 并 `scrollIntoView`；命中数 = 包裹总数。
- **替换（数据）**：统一在源串上做——取 `getContent()`、替换后 `setContent()` 重渲染；重渲染后重新高亮。避免直接改 DOM 与 Vditor(lute AST) 内部模型不同步。
- **匹配基准**：以源串为计数/替换基准（精确），高亮在渲染 DOM 展示（所见即所搜）。源/渲染口径差异（如 Markdown 语法 `#`/`*` 不在渲染文本）作为已知限制写明。
- **降级版（先落地，低风险）**：仅源串查找/替换（Source 模式下高亮 textarea 选区或面板列命中行），放弃渲染区高亮跳转——仍满足实时匹配+命中数+单/全替换。建议先降级版跑通，再迭代混合版。

**交互/边界**：
- 唤起：`Ctrl/Cmd+F`（文档级捕获并 `preventDefault` 屏蔽浏览器原生查找）；`Ctrl+H` 展开替换区（可选）；面板内 `Esc` 关闭。
- 实时：输入即重算（防抖 ~120ms），显示 `当前/总数`；无匹配 `0/0` 并禁用跳转/替换。
- 跳转：`Enter`/`F3` 下一处，`Shift+Enter`/`Shift+F3` 上一处；当前命中滚动可见并高亮。
- 替换："替换"改当前并跳下一处；"全部替换"源串全局替换后 `setContent`；支持大小写敏感/整词/正则（正则替换支持 `$1`）。
- **快捷键冲突**：`Ctrl+F` 须在捕获阶段 `preventDefault` 优先于 Vditor contenteditable 键处理；面板输入框内 `Ctrl+F` 不重复唤起；不影响既有 `Ctrl/Cmd+S`。
- **搜索状态**：模块级状态 `{term, opts, matches[], index, dirty}`；打开时若有选区预填 term；切换文件/渲染模式/文档被外部改动时清空高亮与状态（防陈旧命中）。
- **跨元素匹配**：逐文本节点匹配；命中跨多元素（如 `<strong>` 截断）按每节点独立处理（已知限制）。
- **大文档**：DOM 遍历随文档增大上升，可对超长文档限遍历/丢帧；替换走源串不遍历 DOM，性能可控。
- **关闭恢复**：`Esc`/关闭把所有 `<mark>` unwrap 还原为文本节点（必须精确还原，否则污染编辑器 DOM）。

**验收**：`Ctrl+F` 唤起且屏蔽原生；实时命中数与位置；上/下跳转当前命中可见高亮；单/全替换正确（含正则/`$1`/大小写/整词）；`Esc` 关闭且 DOM 高亮清除、内容无损；切文件/模式后状态正确失效。

---

## 4. 实施顺序与依赖

| 顺序 | 需求 | 文件 | 风险 | 说明 |
|---|---|---|---|---|
| 1 | ① 并发保存修复 | `server.py` | 低 | 后端独立，先稳地基；含防回归并发测试 |
| 2 | ② 文件名显示 | `index.html` | 低 | 纯 CSS+少量 JS |
| 3a | ③ 查找替换（降级版） | `index.html` | 中 | 源串查找/替换，先跑通 |
| 3b | ③ 查找替换（混合高亮版） | `index.html` | 中高 | 渲染 DOM 高亮，重点防 Vditor 状态不同步 |

- 每项独立可测、独立短分支（`feat/...`/`fix/...`），合并回 `main` 即删。
- ① 与 ②③ 分属 `server.py` / `index.html`，互不冲突；②③ 同在 `index.html` 单体大文件，建议串行小步提交，避免合并冲突。

## 5. 版本 / 门禁 / 合规

- `tools/bump_version.py` 升 1.6.0（两源一致）。
- 改动 `vditor-fpk/app/` 后至少 `python tests/test_pkg.py && python tests/test_core.py`；交付前 `rm -rf vditor-fpk/app/__pycache__ && python tests/run_all.py --all` 必须 0 失败。
- 新增/改动 `.py` 须 SPDX 头（`# Copyright (c) 2026 mian38` + `# SPDX-License-Identifier: MIT`）；前端按钮须挂变体类；`#confirm-mask` 反色不"修正"。
- 双 changelog：`CHANGELOG.md`(开发者) + `CHANGELOG_USER.md`(用户，分类仅 新增/优化/修复/更改，一句话)；发布前按 `AGENTS.md §9` 逐条比对 manifest changelog 与用户版条目。
- 用户版 changelog：① 用「修复」、②③ 用「新增」。
- **人在环**：agent 负责修复+测试+打包，交付物为**未发布测试版**（四段式 `1.6.0.N`）；实机验证由用户（mian38）完成；agent 不自行打 tag/建 Release/上传。

## 6. 跨 agent 注意事项

- 三需求中 ① 在后端、②③ 在前端，**文件级隔离**，可并行开发；但 `index.html` 为单体外联大文件（约 3675 行），②③ 若并行改同一文件易冲突，建议串行或极小步 PR。
- ① 的详细方案以 `fix_concurrent_save.md` 为准；本文件为其合并摘要。
- 凡改动保存/内容读写，务必保留 `getContent/setContent` 访问层与就绪判断（1.4.3 教训），并用 `node+vm` 真调防跨作用域 `ReferenceError` 漏网（遵循 `AGENTS.md §2`）。
- 验收依赖用户实机；agent 交付前确保本地测试门禁 0 失败，避免浪费一次实机安装。
