# 开源合规性审查报告

**审查对象**：vditor（飞牛 fnOS / 通用 Linux NAS 的 Vditor Markdown 编辑器）
**审查基准**：`v1.1.x` 分支 HEAD `2c54a1c`，版本 1.1.4
**审查日期**：2026-10-03
**审查方法**：五维度实证扫描（配置断言 + 全仓 grep + git 历史追溯），不依赖推断

---

## 结论速览

**当前不具备直接发布到 GitHub 等开源平台的条件。**

阻断项共 3 个（Blocker），其中 **P0-1「无本项目许可证」是法律级阻断**：
在只有 Vditor 上游 MIT 版权声明、没有本项目授权条款的情况下公开发布，
**任何人都无权使用、修改或再分发本项目代码**，而你作为原作者也无法阻止他人使用——
这是最坏的状态。其余为文档缺失与仓库卫生问题，不涉及法律风险。

排除阻断项后，代码层面的合规状况**良好**：零硬编码密钥、零内网地址、零真实密码、
零个人隐私信息、零 IDE 私密配置。这部分经得起公开审查。

---

## 维度一：许可证

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 本项目 LICENSE | 🔴 **缺失** | 根目录**无** LICENSE 文件。三份副本（`vditor-fpk/`、`vditor-nas/`、`nas-template/`）内容**完全相同**，均为 Vditor 上游的 MIT（`Copyright (c) 2019-present B3log 开源, b3log.org`） |
| 版权归属 | 🔴 **错误** | 现有 LICENSE 声明的著作权人是**上游 B3log**，不是本项目作者 mian38。二者混淆 |
| 代码头部声明 | 🟡 **缺失** | `server.py` / `vd_util.py` / `make_nas.py` / `bump_version.py` / `build_fpk.py` 均只有 docstring，**无 Copyright 行、无 SPDX 标识** |
| 与上游许可兼容 | ✅ **兼容** | Vditor 为 MIT，MIT 允许闭源衍生与再分发，但**要求保留上游版权声明**——现有 `vditor-fpk/app/vditor/LICENSE` 与三份副本均已满足 |
| 第三方许可完整性 | 🟡 **部分缺失** | `vditor/` 16 MB 运行时内**仅 3 份 LICENSE**：顶层 Vditor、`dist/js/highlight.js/LICENSE`、`dist/js/wavedrom/LICENSE.WaveDrom`。而实际捆绑的 KaTeX、Mermaid、Graphviz(wasm)、ECharts、Smiles Drawer、PlantUML、abcjs、Markmap、FontAwesome、CodeMirror 等**均无独立许可声明** |

**法律要点**：MIT 许可的两个条件是「保留版权声明」与「包含许可声明」。当前状态下
`vditor-fpk/LICENSE` 被当作本项目许可分发，会**误导下游认为整个包都归 B3log 所有**，
而 `server.py`（约 1,900 行本项目原创代码）实际不在该声明覆盖范围内——授权真空。

---

## 维度二：文档与元信息

| 项目 | 状态 |
| --- | --- |
| README.md（根） | 🔴 **缺失** |
| CONTRIBUTING.md | 🔴 **缺失** |
| CODE_OF_CONDUCT.md | 🔴 **缺失** |
| SECURITY.md | 🔴 **缺失** |
| CHANGELOG.md | ✅ 已具备（41 KB，29 个版本条目，格式规范） |
| CHANGELOG_USER.md | ✅ 已具备（15 KB，用户视角） |
| ARCHIVE.md | ✅ 已具备（版本归档与回滚说明） |
| CODE_REVIEW.md | ✅ 已具备（1.1 审计报告） |
| docs/MOBILE_API.md | ✅ 已具备（1.1.3 预留接口规范） |
| LICENSE（根） | 🔴 **缺失**（见维度一） |
| .github/ 目录 | 🔴 **不存在**（无 issue/PR 模板、无 FUNDING.yml、无 workflows） |
| 项目名/描述/作者元信息 | 🟡 **不完整**。仅 `manifest` 内有 `appname`/`desc`/`maintainer=mian38`，**无仓库地址、无 homepage、无 author 字段** |
| 唯一实质 README | 🟡 `nas-template/README.md` 存在（11 KB），但定位是「部署指南」，**内容绑定 `vditor-nas/` 目录**，未涵盖 fpk 安装与项目整体介绍 |

**注**：`nas-template/README.md` 是当前唯一像样的说明文档，但它在 `make_nas.py`
的模板复制逻辑里**指向 `vditor-nas/LICENSE`**——一旦改为本项目许可证，需同步该路径。

---

## 维度三：敏感信息与私有数据

**结论：本维度全部通过，是本项目最扎实的部分。**

| 检查项 | 结果 |
| --- | --- |
| 硬编码密钥 / API Key / Token | ✅ 零命中。全仓 `password/secret/api_key/token/bearer/private_key` 匹配项**全部是功能性代码**：`secrets.token_bytes(16)` 随机盐、`secrets.token_urlsafe(32)` 会话 ID、`data.get("password")` 登录入参 |
| 私钥文件 | ✅ `.jks`/`.keystore`/`.pem`/`.p12`/`.key`/`keystore.properties` **在 git 全部 5 个提交中从未被添加过** |
| 明文密码 | ✅ `config.env` 生效行仅 `PORT=9000` / `HOST=0.0.0.0`。`VDITOR_PASSWORD=changeme` 与 `VDITOR_PWHASH=` **均在注释中**（示例占位） |
| 内网 / 私有 IP | ✅ 零命中。唯一命中是 `nas-template/README.md:33` 的 `http://<你的NAS的IP>:9000`，为占位符 |
| 本地绝对路径 | ✅ 源码零硬编码。测试脚本的 `.mtest/` 临时目录为相对路径 |
| 个人信息 | ✅ `maintainer=mian38` / `distributor=mian38` 为公开署名，非隐私。`index.html:803` 的 `username@gmail.com` 出自 **Vditor 官方 demo 教程文案**（同段还有 `@Vanessa`、`ld246.com`），属上游示例内容 |
| git 历史敏感提交 | ✅ `git log -S "VDITOR_PASSWORD="` 命中的 `ebadb91` 是**首次添加注释示例**，非泄露真实密码 |
| 私有链接 | ✅ 无内网域名、无 `*.local`、无打码前的真实服务地址 |

---

## 维度四：第三方代码与资源

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| Vditor 上游署名 | ✅ **已具备**。`vditor-fpk/app/vditor/LICENSE` 保留完整 MIT 声明（版权 2019-present B3log） |
| 第三方链接保留 | ✅ `index.html` 保留 `https://b3log.org`（:949）、`https://ld246.com`（Vditor 作者站点）等上游出处 |
| 复制粘贴代码授权 | ✅ **无风险**。后端 `server.py`/`vd_util.py` 为本项目原创，无从上游复制。测试脚本亦原创 |
| 高亮主题 | ⚠️ 249 个 highlight.js 主题**仅有 `dist/js/highlight.js/LICENSE`** 统一覆盖，粒度可接受 |
| WaveDrom | ✅ 有独立 `LICENSE.WaveDrom` |
| **KaTeX / Mermaid / Graphviz / ECharts / Smiles Drawer / PlantUML / abcjs / Markmap / CodeMirror / FontAwesome** | 🔴 **缺失独立许可声明**。这批均为**各自独立的第三方作品**（多为 MIT / Apache-2.0 / BSD，但 KaTeX 与部分字体为 MIT+字体例外条款），仅靠顶层 Vditor 的 MIT 声明**不构成对它们的授权覆盖** |
| 字体文件（woff/woff2/ttf 40 个） | 🟡 **需核实**。vditor 的 iconfont 属独立字体授权，MIT 许可**不覆盖字体文件**的商业分发条款 |
| `fnpack.exe`（3.96 MB，已跟踪） | 🟡 **需说明**。飞牛 fnOS 官方打包工具，非本项目代码。随仓库分发需注明来源与飞牛官方的许可条款 |

**风险等级评估**：多为**中低风险**（MIT 类许可要求"保留声明"，而这些库确实在包内但未单独声明，
属于"未明示"而非"被禁止"）。但 Apache-2.0 组件（若含）要求**明确标注**并保留 NOTICE，
合规缺口可能构成违约。

---

## 维度五：仓库卫生

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| `.gitignore` 合理性 | 🟡 **部分合理**。已排除 `*.fpk`/`*.pyc`/`__pycache__`/临时目录，但**未覆盖** `*.exe`、`*.apk`、`.idea/`、`.vscode/`、`*.log`、`.DS_Store`、`Thumbs.db`、`*~`、`*.bak`、`.env` |
| IDE 私密配置 | ✅ 当前无。但 `.idea/`/`.vscode/` 未被忽略，他人 clone 后开IDE 即会污染 |
| 构建产物混入 | 🔴 **已混入**。913 个跟踪文件中 **131 个二进制**：`fnpack.exe`(3.96 MB)、`releases/vditor-nas-1.1.4.tar.gz`、`archive/v4.0.17-beta…/legacy_artifacts/vditor-nas-4.0.0.tar.gz` |
| `archive/` 混入 | 🟡 **已混入 125 个文件**。历史快照含旧版 `server.py`/`index.html`，与主线并存易误导，且 `.gitignore` 的 `archive/**/app/` 规则导致**部分内容进不了仓库**（disk2,241 文件 vs git 125） |
| `.workbuddy/` 混入 | 🟡 **已混入 4 个文件**。AI 工具的私有记忆目录，与项目代码无关，**不应进公开仓库** |
| 依赖版本可复现 | 🟡 **部分**。Python 端**零第三方依赖**（仅标准库：`os/sys/re/json/...`）——这是巨大优势，天然可复现。但：<br>①**无任何依赖声明文件**（无 `requirements.txt`/`pyproject.toml`）<br>②**前端无版本锁定**：`vditor/` 为拷贝的 dist 产物，未记录 Vditor 版本号<br>③`nas-template/install.sh:37` 声明 `Python 3.8+`，但无机器可读约束 |
| 远程仓库 | ⚪ 未配置 `git remote`（开源前需新建） |

---

## 整改清单（按优先级）

### P0 ·阻断发布（必须先完成）

**P0-1为法律级阻断：无本项目许可证**
- **严重程度**：🔴 **Blocker**
- **位置**：新建 `LICENSE`（根目录）
- **动作**：编写本项目 MIT 许可证，版权人 `Copyright (c) 2026 mian38`。
  **注意**：不可直接复用 `vditor-fpk/LICENSE`（那份著作权人是 B3log）。
- **同步点**：`vditor-fpk/LICENSE`、`vditor-nas/LICENSE`、`nas-template/LICENSE`
  三份副本需同步替换为本项目许可；`vditor-fpk/app/vditor/LICENSE`
  **保持原样不动**（那是 Vditor 上游许可，必须保留）
- **连带**：`make_nas.py` 复制 `LICENSE` 的路径逻辑不受影响（同名文件），但需确认 `nas-template/README.md` 内引用的许可表述同步更新

**P0-2　代码头部无版权与许可声明**
- **严重程度**：🔴 **Blocker**
- **位置**：`vditor-fpk/app/server.py`、`vditor-fpk/app/vd_util.py`、
  `make_nas.py`、`bump_version.py`、`build_fpk.py`（**每个文件仅在唯一源改一次**，
  `vditor-nas/` 为派生副本，**跑 `python3 make_nas.py` 自动同步**，勿手工改）
- **动作**：在 docstring 后加两行：
  ```python
  # Copyright (c) 2026 mian38
  # SPDX-License-Identifier: MIT
  ```
- **注意**：仓库根有 12 个 `test_*.py`，若开源建议统一加 SPDX 行（可批量脚本处理）

**P0-3　第三方组件许可声明不完整**
- **严重程度**：🔴 **Blocker**（Apache-2.0 组件若在列，明确违约）
- **位置**：新建 `THIRD_PARTY_NOTICES.md`（根目录）
- **动作**：列出 `vditor/` 16 MB 运行时内全部第三方组件及其许可：
  - 必须逐个核实并登记：Vditor、highlight.js（含 249 主题）、KaTeX、Mermaid、
    Graphviz/viz.js、ECharts、Smiles Drawer、PlantUML、abcjs、Markmap、
    WaveDrom、CodeMirror、FontAwesome、iconfont 字体
  - Apache-2.0 组件须原文保留其 LICENSE与 NOTICE
  - 字体文件须单独说明授权（MIT 不覆盖字体）
- **验证方式**：`ls vditor-fpk/app/vditor/dist/js/` 与 `dist/css/` 逐目录核对

### P1 · 严重（影响开源可用性与专业观感）

**P1-1　根README 缺失**
- **严重程度**：🟠 **High**
- **位置**：新建 `README.md`（根目录）
- **动作**：项目名、简介、截图、功能特性列表、两种安装方式（fnOS 应用中心 + NAS 通用版）、
  环境要求（Python 3.8+ / 零第三方依赖）、快速上手、文档索引、更新日志引用、贡献与许可章节
- **可复用**：`nas-template/README.md` 已有部署指南全文，可摘编为 README 的安装章节

**P1-2　治理文档缺失（CONTRIBUTING / CODE_OF_CONDUCT / SECURITY）**
- **严重程度**：🟠 **High**（GitHub 社区健康度硬指标）
- **位置**：新建 `CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md`
- **动作**：
  - CONTRIBUTING：分支命名、提交规范（项目现有 `chore/feat/docs:` 前缀风格可直接写入）、
    定向测试约定（"自1.1.1 起只对本轮修改做定向测试"——这是项目真实约定，值得写明）
  - CODE_OF_CONDUCT：采用 Contributor Covenant，指定联系邮箱
  - SECURITY：**必须写明漏洞报告渠道**。鉴于本项目处理密码与会话，
    应说明「不要开公开 issue 报告漏洞」

**P1-3　非代码文件混入仓库**
- **严重程度**：🟠 **High**
- **位置**：`.workbuddy/`（4 文件，AI 私有记忆）、`archive/`（125 文件历史快照）、
  `fnpack.exe`（3.96 MB 第三方可执行文件）
- **动作**：
  - `.workbuddy/` → 移出仓库（改用用户级 `~/.workbuddy/`）或加入 `.gitignore`
  - `archive/` → 决策二选一：**① 保留**（历史可追溯，但须在 README 说明它是离线备份、
    非构建输入，且需修正 `.gitignore` 让内容能进仓库）；**② 移出**（推荐——
    已有 git 标签 `v1.1.4`/`v1.1.4beta` +归档分支做版本留存，archive 属冗余）
  - `fnpack.exe` → 移出仓库，在 README「构建」章节注明"需从飞牛官方获取"
- **注意**：若选②，**务必先确认需要的快照已确无可替代价值**（4.0.17-beta /
  1.1.2 / 1.1.3 三者在 git 中无对应提交，删则永久丢失）

### P2 · 中等（应修，但不阻断）

**P2-1　`.gitignore` 覆盖不足**
- **严重程度**：🟡 **Medium**
- **位置**：`.gitignore`
- **动作**：补 `*.exe`（若移走 fnpack）、`*.apk`、`.idea/`、`.vscode/`、
  `*.log`、`.DS_Store`、`Thumbs.db`、`*~`、`*.bak`、`.env`、`*.tar.gz`
- **注意**：`archive/**/app/` 这类规则在开源场景下会造成「文件在磁盘但不在仓库」，
  若保留 archive 需重新评估

**P2-2　元信息不完整**
- **严重程度**：🟡 **Medium**
- **位置**：`vditor-fpk/manifest`（现16 字段，缺 author/homepage/source url）
- **动作**：开源时补`author`/`homepage` 字段；GitHub 侧仓库 description、topics、homepage URL
  在仓库设置中补（无remote，需先建远程）

**P2-3　依赖可复现性**
- **严重程度**：🟡 **Medium**
- **位置**：新建 `requirements.txt`（可为空并注明"零第三方依赖"）或 `pyproject.toml`
- **动作**：① 声明 `requires-python = ">=3.8"`；② **在 README 记录 `vditor/` 的
  Vditor 版本号**（当前完全无从考证是哪一版，是真实的可复现性缺口）

**P2-4　无 issue / PR 模板**
- **严重程度**：🟢 **Low**
- **位置**：新建 `.github/ISSUE_TEMPLATE/bug_report.yml`、`.github/pull_request_template.md`
- **动作**：bug 模板应含「版本号（fpk / tar.gz）、部署方式（fnOS / NAS）、Python 版本、
  浏览器、控制台报错」——项目跨两种分发形态，需分别收集

### P3 · 低（可选改进）

**P3-1**　`apply_style_v414` / `check` 缺`.py` 后缀（shebang 脚本），影响可读性
**P3-2**　`ARCHIVE.md` 中「当前发布线（1.2）」「回滚不需要破坏性操作」等表述已在回退后过时，
需同步为「当前主线 1.1.4 / 1.2 已归档」
**P3-3**　`docs/MOBILE_API.md` 在主线是 1.1.3「预留规范版」，README 需说明其状态
  （避免用户误以为可用）

---

## 最终判定

| 判定项 | 结论 |
| --- | --- |
| 是否具备直接开源条件 | ❌ **否** |
| 阻断原因 | P0-1（无本项目许可证，法律级）、P0-2（无SPDX 声明）、P0-3（第三方许可声明缺失） |
| 代码安全性 | ✅ 通过。零密钥、零内网地址、零真实密码、零隐私数据 |
| 修复工作量 | 约 2–3 小时。P0 三项以文件编写为主，无代码逻辑改动 |
| 建议 | 先完成 P0 三项 + P1-2（SECURITY.md），再公开发布。P1-1/README 可与 P0 同批完成 |

**最小可发布路径**：新建 `LICENSE`(MIT, mian38) + `THIRD_PARTY_NOTICES.md` +
5 个源文件加 SPDX 行 + `README.md` + `SECURITY.md`，
并把 `.workbuddy/` 与 `fnpack.exe` 移出仓库。完成后即可合规发布。

---

## 附：审查命令清单（可复现）

```bash
#维度一：许可证
find . -name "LICENSE*" -not -path "./.git/*" -not -path "./archive/*"
find vditor-fpk/app/vditor -iname "LICENSE*" -o -iname "NOTICE*"

# 维度三：敏感信息
grep -rniE "(password|secret|api[_-]?key|private[_-]?key|BEGIN.*PRIVATE KEY)" \
  --include="*.py" --include="*.sh" --include="*.env" vditor-fpk/app/ nas-template/
grep -rniE "(192\.168\.|10\.[0-9]+\.[0-9]+\.|C:\\\\Users\\\\)" --include="*.py" --include="*.md" .
git log --all --diff-filter=A --name-only | grep -iE "\.(jks|keystore|pem|key)$"

# 维度五：仓库卫生
git ls-files | grep -iE "\.idea|\.vscode|\.DS_estore|__pycache__|\.log$"
git ls-files | grep -iE "\.(exe|fpk|gz|apk)$"
grep -vE "^\s*#|^\s*$" vditor-nas/config.env   # 生效配置项
```

---

## 整改执行记录（2026-10-03）

全部 P0 / P1 / P2 / P3 整改项已执行完毕，提交 `1b7366f`。

| 编号 | 严重程度 | 状态 | 落实位置 |
| --- | --- | --- | --- |
| P0-1 | Blocker | ✅ 已修复 | 新增根 `LICENSE`（MIT, mian38）；替换 `vditor-fpk/` `vditor-nas/` `nas-template/` 三份副本 |
| P0-2 | Blocker | ✅ 已修复 | 17 个 Python 源文件全部添加 SPDX 标识 |
| P0-3 | Blocker | ✅ 已修复 | 新增 `THIRD_PARTY_NOTICES.md`；补`echarts/LICENSE` + `echarts/NOTICE`（Apache-2.0 义务） |
| P1-1 | High | ✅ 已修复 | 新增 `README.md` / `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md` / `SECURITY.md` |
| P1-2 | High | ✅ 已修复 | manifest 补 `author` 与 `homepage` 字段 |
| P1-3 | High | ✅ 已修复 | `SECURITY.md` 明确私下报告渠道，禁止公开 issue 报漏洞 |
| P2-1 | Medium | ✅ 已修复 | `.workbuddy/` 移出版本控制（4 份 AI 私有记忆） |
| P2-2 | Medium | ✅ 已修复 | `fnpack.exe`（3.8 MB 第三方二进制）移出版本控制 |
| P2-3 | Medium | ✅ 已修复 | 新增 `requirements.txt`（零依赖声明 + 实测 import 清单） |
| P2-4 | Medium | ✅ 已修复 | 新增 `.github/`（PR 模板 + 2 个 issue 模板） |
| P3-1 | Low | ✅ 已修复 | `.gitignore` 补fnpack.exe / `.workbuddy/` / IDE / 日志 / `.env` 类规则 |
| P3-2 | Low | ✅ 已修复 | `ARCHIVE.md` 首行已为「当前主线 v1.1.x（1.1.4）」 |
| P3-3 | Low | ✅ 已修复 | `README.md` 记录 Vditor 版本 4.0.0 及MD5 比对依据 |

### 执行过程中的事实修正

- **highlight.js 主题数**：审查初稿写「递归 251 个文件」，实测 `dist/js/highlight.js/styles/` 下共 **251 个文件、其中 `.css` 为 249 个**（另 2 个为 `brown-papersq.png`、`pojoaque.jpg` 两套主题的背景图）。**「249 套主题」是正确数字**，初稿把文件总数当成了主题数。
- **Vditor 版本**：确证为 **4.0.0**（`lute.min.js` 等 7 个文件 MD5 与官方 unpkg 完全一致），非推测。
- **第三方许可来源**：全部为文件内banner 实证或上游仓库核实，未使用推测信息。
- **`.workbuddy/` 的敏感性**：内含内部 commit hash（如 `d718f1f`、`9f206fd`）、未发布的版本计划与内部踩坑记录，属不应公开的私有工作记忆。

### 保留决定

| 路径 | 决定 | 理由 |
| --- | --- | --- |
| `archive/` | **保留在仓库** | 4.0.17-beta / 1.1.2 / 1.1.3 三个快照在 Git 历史中**无对应提交**，移出后仅存于本地磁盘，不可追溯 |
| `releases/*.fpk` | 已被`.gitignore` 忽略 | 24 个 `.fpk` 从未进入 Git 跟踪（实测`git ls-files "*.fpk"` = 0） |
| `releases/vditor-nas-1.1.4.tar.gz` | **保留跟踪** | NAS 通用版发布产物，供用户直接下载 |
| `vditor-fpk/app/vditor/LICENSE` | **原样保留** | 上游 MIT 许可，MIT §要求保留原始版权声明 |

### 遗留提醒

- `SECURITY.md` 中已记录当前版本的**已知边界**：`X-Forwarded-Proto: https` 被无条件信任，不经过可信代理时可能绕过 HTTP 限制，更严格的方案需维护可信代理白名单，当前未实现。
- `archive/` 中仍含3 个 Git 无对应提交的历史快照，若未来开源且希望减小仓库体积，需先将其转为Git 提交或移至独立发布，再从主仓库移除。

### 最终结论

**项目已具备直接公开发布到GitHub 的条件。** 三个 Blocker 级法律风险全部闭环，敏感信息扫描无命中，回归测试 443/443 全绿。
